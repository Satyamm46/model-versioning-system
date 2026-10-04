"""All business logic lives here (routes stay thin)."""
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.app import config
from backend.app.logger import log
from backend.database.db import get_conn
from backend.services.validation import has_valid_extension, validate_model_file


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "model"


# ---------------------------------------------------------------- models
def create_model(data: dict) -> dict:
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO models (name, description, model_type, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (data["name"], data["description"], data["model_type"], data["created_by"], now()),
            )
        except sqlite3.IntegrityError:
            raise ServiceError(409, "A model with this name already exists")
        row = conn.execute("SELECT * FROM models WHERE id = ?", (cur.lastrowid,)).fetchone()
    log.info("Model registered: %s by %s", data["name"], data["created_by"])
    return dict(row)


def list_models() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT m.*,
                 (SELECT COUNT(*) FROM model_versions v WHERE v.model_id = m.id) AS version_count,
                 (SELECT version FROM model_versions v
                   WHERE v.model_id = m.id AND v.status = 'PRODUCTION') AS production_version
               FROM models m ORDER BY m.id"""
        ).fetchall()
    return [dict(r) for r in rows]


def _model_or_404(conn, model_id: int):
    row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    if not row:
        raise ServiceError(404, "Model not found")
    return row


def find_rollback_target(conn, model_id: int):
    """Previous stable = the highest ARCHIVED version below the current production
    version that was successfully deployed at some point."""
    current = conn.execute(
        "SELECT version FROM model_versions WHERE model_id = ? AND status = 'PRODUCTION'", (model_id,)
    ).fetchone()
    if not current:
        return None
    return conn.execute(
        """SELECT v.* FROM model_versions v
           WHERE v.model_id = ? AND v.version < ? AND v.status = 'ARCHIVED'
             AND EXISTS (SELECT 1 FROM deployments d
                         WHERE d.model_version_id = v.id AND d.status = 'SUCCESS')
           ORDER BY v.version DESC LIMIT 1""",
        (model_id, current["version"]),
    ).fetchone()


def get_model(model_id: int) -> dict:
    with get_conn() as conn:
        model = dict(_model_or_404(conn, model_id))
        model["version_count"] = conn.execute(
            "SELECT COUNT(*) FROM model_versions WHERE model_id = ?", (model_id,)
        ).fetchone()[0]
        prod = conn.execute(
            "SELECT * FROM model_versions WHERE model_id = ? AND status = 'PRODUCTION'", (model_id,)
        ).fetchone()
        model["production_version"] = prod["version"] if prod else None
        model["production_accuracy"] = prod["accuracy"] if prod else None
        last = conn.execute(
            """SELECT d.deployment_time FROM deployments d
               JOIN model_versions v ON v.id = d.model_version_id
               WHERE v.model_id = ? AND d.status = 'SUCCESS' ORDER BY d.id DESC LIMIT 1""",
            (model_id,),
        ).fetchone()
        model["last_deployment"] = last["deployment_time"] if last else None
        target = find_rollback_target(conn, model_id)
        model["rollback_target"] = target["version"] if target else None
    return model


def delete_model(model_id: int) -> None:
    with get_conn() as conn:
        model = _model_or_404(conn, model_id)
        prod = conn.execute(
            "SELECT 1 FROM model_versions WHERE model_id = ? AND status = 'PRODUCTION'", (model_id,)
        ).fetchone()
        if prod:
            raise ServiceError(409, "Cannot delete a model that has a PRODUCTION version")
        conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
    shutil.rmtree(config.storage_dir() / slugify(model["name"]), ignore_errors=True)
    log.info("Model deleted: %s", model["name"])


# -------------------------------------------------------------- versions
def _save_upload(upload, dest: Path) -> int:
    limit = config.max_upload_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    total, too_big = 0, False
    with open(dest, "wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                too_big = True
                break
            out.write(chunk)
    if too_big:
        shutil.rmtree(dest.parent, ignore_errors=True)
        raise ServiceError(413, "File is larger than the allowed upload size")
    return total


def create_version(model_id: int, upload, accuracy: Optional[float],
                   created_by: str, change_notes: str) -> dict:
    filename = upload.filename or ""
    if not has_valid_extension(filename):
        log.warning("Validation failed: bad extension for %s", filename)
        raise ServiceError(400, "Invalid file type. Allowed extensions: .pkl, .joblib")
    if accuracy is not None and not 0 <= accuracy <= 100:
        raise ServiceError(400, "Accuracy must be between 0 and 100")

    with get_conn() as conn:
        model = _model_or_404(conn, model_id)
        next_v = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM model_versions WHERE model_id = ?", (model_id,)
        ).fetchone()[0]
        rel_path = Path(slugify(model["name"])) / f"v{next_v}" / f"model{Path(filename).suffix.lower()}"
        dest = config.storage_dir() / rel_path
        size = _save_upload(upload, dest)

        ok, message = validate_model_file(dest)
        status = "TESTING" if ok else "FAILED"
        try:
            cur = conn.execute(
                """INSERT INTO model_versions (model_id, version, file_path, file_size, accuracy, status,
                       change_notes, validation_message, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (model_id, next_v, rel_path.as_posix(), size, accuracy, status,
                 change_notes, message, created_by, now()),
            )
        except sqlite3.IntegrityError:
            shutil.rmtree(dest.parent, ignore_errors=True)
            raise ServiceError(409, "Duplicate version number, please retry")
        row = conn.execute("SELECT * FROM model_versions WHERE id = ?", (cur.lastrowid,)).fetchone()

    log.info("Model uploaded: %s", model["name"])
    log.info("Version created: %s v%s (%s)", model["name"], next_v, status)
    if not ok:
        log.warning("Validation failed: %s v%s - %s", model["name"], next_v, message)
    return dict(row)


def list_versions(model_id: int) -> list:
    with get_conn() as conn:
        _model_or_404(conn, model_id)
        rows = conn.execute(
            "SELECT * FROM model_versions WHERE model_id = ? ORDER BY version DESC", (model_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_version(version_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT v.*, m.name AS model_name FROM model_versions v
               JOIN models m ON m.id = v.model_id WHERE v.id = ?""",
            (version_id,),
        ).fetchone()
    if not row:
        raise ServiceError(404, "Version not found")
    return dict(row)


def set_status(version_id: int, status: str) -> dict:
    status = status.upper()
    if status not in ("DRAFT", "TESTING", "STAGING", "ARCHIVED"):
        raise ServiceError(400, "Status can only be set to DRAFT, TESTING, STAGING or ARCHIVED "
                                "(use promote for PRODUCTION)")
    with get_conn() as conn:
        row = conn.execute("SELECT status FROM model_versions WHERE id = ?", (version_id,)).fetchone()
        if not row:
            raise ServiceError(404, "Version not found")
        if row["status"] in ("PRODUCTION", "FAILED"):
            raise ServiceError(409, f"A {row['status']} version cannot change status this way")
        conn.execute("UPDATE model_versions SET status = ? WHERE id = ?", (status, version_id))
    return get_version(version_id)


# ------------------------------------------------------ deploy / rollback
def _deploy_file(model_name: str, rel_path: str) -> None:
    """Publish the model file to deployed/<slug>/ (this is the 'live' copy)."""
    src = config.storage_dir() / rel_path
    target = config.deploy_dir() / slugify(model_name)
    target.mkdir(parents=True, exist_ok=True)
    for old in target.glob("model.*"):
        old.unlink()
    shutil.copy2(src, target / src.name)


def _record_deployment(conn, version_id, action, status, user, notes=""):
    conn.execute(
        "INSERT INTO deployments (model_version_id, action, status, deployed_by, deployment_time, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (version_id, action, status, user, now(), notes),
    )


def promote(version_id: int, user: str) -> dict:
    error = None
    with get_conn() as conn:
        v = conn.execute(
            """SELECT v.*, m.name AS model_name FROM model_versions v
               JOIN models m ON m.id = v.model_id WHERE v.id = ?""",
            (version_id,),
        ).fetchone()
        if not v:
            raise ServiceError(404, "Version not found")
        if v["status"] == "FAILED":
            raise ServiceError(400, "Failed versions cannot be promoted")
        if v["status"] == "PRODUCTION":
            raise ServiceError(409, "This version is already in production")

        log.info("Deployment started: %s v%s by %s", v["model_name"], v["version"], user)
        ok, message = validate_model_file(config.storage_dir() / v["file_path"])
        if ok:
            try:
                _deploy_file(v["model_name"], v["file_path"])
            except OSError as exc:
                ok, message = False, f"Could not publish model file: {exc}"

        if not ok:
            conn.execute("UPDATE model_versions SET status = 'FAILED', validation_message = ? WHERE id = ?",
                         (message, version_id))
            _record_deployment(conn, version_id, "DEPLOYMENT", "FAILED", user, message)
            error = message
        else:
            conn.execute("UPDATE model_versions SET status = 'ARCHIVED' "
                         "WHERE model_id = ? AND status = 'PRODUCTION'", (v["model_id"],))
            conn.execute("UPDATE model_versions SET status = 'PRODUCTION' WHERE id = ?", (version_id,))
            _record_deployment(conn, version_id, "DEPLOYMENT", "SUCCESS", user, message)

    if error:
        log.warning("Deployment failed: %s v%s - %s", v["model_name"], v["version"], error)
        raise ServiceError(400, f"Promotion blocked: {error}")
    log.info("Model promoted: %s v%s is now PRODUCTION", v["model_name"], v["version"])
    log.info("Deployment completed: %s v%s", v["model_name"], v["version"])
    return get_version(version_id)


def rollback(model_id: int, user: str, reason: str = "", to_version: Optional[int] = None) -> dict:
    with get_conn() as conn:
        model = _model_or_404(conn, model_id)
        current = conn.execute(
            "SELECT * FROM model_versions WHERE model_id = ? AND status = 'PRODUCTION'", (model_id,)
        ).fetchone()
        if not current:
            raise ServiceError(400, "No production version exists, nothing to roll back")

        if to_version is not None:
            target = conn.execute(
                "SELECT * FROM model_versions WHERE model_id = ? AND version = ?", (model_id, to_version)
            ).fetchone()
            if not target:
                raise ServiceError(404, f"Version v{to_version} not found")
            if target["status"] in ("FAILED", "PRODUCTION"):
                raise ServiceError(400, f"Cannot roll back to a {target['status']} version")
        else:
            target = find_rollback_target(conn, model_id)
            if not target:
                raise ServiceError(400, "No previous stable version available for rollback")

        try:
            _deploy_file(model["name"], target["file_path"])
        except OSError as exc:
            _record_deployment(conn, target["id"], "ROLLBACK", "FAILED", user, str(exc))
            raise ServiceError(500, f"Rollback failed: {exc}")

        conn.execute("UPDATE model_versions SET status = 'ARCHIVED' WHERE id = ?", (current["id"],))
        conn.execute("UPDATE model_versions SET status = 'PRODUCTION' WHERE id = ?", (target["id"],))
        _record_deployment(conn, target["id"], "ROLLBACK", "SUCCESS", user,
                           reason or f"Rollback v{current['version']} -> v{target['version']}")
        conn.execute(
            "INSERT INTO rollbacks (model_id, from_version, to_version, performed_by, rollback_time, reason) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (model_id, current["version"], target["version"], user, now(), reason),
        )
    log.info("Rollback performed: %s v%s -> v%s by %s", model["name"],
             current["version"], target["version"], user)
    return {
        "message": "Rollback successful.",
        "from_version": current["version"],
        "to_version": target["version"],
        "summary": f"Production version changed: v{current['version']} \u2192 v{target['version']}",
    }


# ------------------------------------------------- history, compare, stats
def list_deployments(model_id: Optional[int] = None) -> list:
    sql = """SELECT d.*, v.version, m.name AS model_name, m.id AS model_id
             FROM deployments d
             JOIN model_versions v ON v.id = d.model_version_id
             JOIN models m ON m.id = v.model_id"""
    params: tuple = ()
    with get_conn() as conn:
        if model_id is not None:
            _model_or_404(conn, model_id)
            sql += " WHERE m.id = ?"
            params = (model_id,)
        rows = conn.execute(sql + " ORDER BY d.id DESC", params).fetchall()
    return [dict(r) for r in rows]


def list_rollbacks(model_id: int) -> list:
    with get_conn() as conn:
        _model_or_404(conn, model_id)
        rows = conn.execute(
            "SELECT * FROM rollbacks WHERE model_id = ? ORDER BY id DESC", (model_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def compare_versions(model_id: int, a: int, b: int) -> dict:
    with get_conn() as conn:
        model = _model_or_404(conn, model_id)
        rows = {}
        for num in (a, b):
            r = conn.execute(
                "SELECT * FROM model_versions WHERE model_id = ? AND version = ?", (model_id, num)
            ).fetchone()
            if not r:
                raise ServiceError(404, f"Version v{num} not found")
            rows[num] = dict(r)
    acc_a, acc_b = rows[a]["accuracy"], rows[b]["accuracy"]
    improvement = round(acc_b - acc_a, 2) if acc_a is not None and acc_b is not None else None
    return {"model": model["name"], "a": rows[a], "b": rows[b], "accuracy_improvement": improvement}


def dashboard() -> dict:
    with get_conn() as conn:
        count = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        rows = conn.execute(
            """SELECT v.*, m.name AS model_name FROM model_versions v
               JOIN models m ON m.id = v.model_id ORDER BY v.id DESC LIMIT 50"""
        ).fetchall()
        return {
            "total_models": count("SELECT COUNT(*) FROM models"),
            "total_versions": count("SELECT COUNT(*) FROM model_versions"),
            "production_models": count("SELECT COUNT(*) FROM model_versions WHERE status = 'PRODUCTION'"),
            "failed_versions": count("SELECT COUNT(*) FROM model_versions WHERE status = 'FAILED'"),
            "versions": [dict(r) for r in rows],
        }
