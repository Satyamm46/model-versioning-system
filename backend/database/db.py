"""SQLite access. Plain sqlite3 keeps the project easy to explain in a viva."""
import sqlite3
from contextlib import contextmanager

from backend.app.config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    model_type  TEXT DEFAULT '',
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_versions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id           INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    version            INTEGER NOT NULL,
    file_path          TEXT NOT NULL,
    file_size          INTEGER NOT NULL DEFAULT 0,
    accuracy           REAL,
    status             TEXT NOT NULL CHECK (status IN
                       ('DRAFT','TESTING','STAGING','PRODUCTION','ARCHIVED','FAILED')),
    change_notes       TEXT DEFAULT '',
    validation_message TEXT DEFAULT '',
    created_by         TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    UNIQUE (model_id, version)
);

-- Database-level guarantee: at most ONE production version per model.
CREATE UNIQUE INDEX IF NOT EXISTS one_production_per_model
    ON model_versions (model_id) WHERE status = 'PRODUCTION';

CREATE TABLE IF NOT EXISTS deployments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version_id INTEGER NOT NULL REFERENCES model_versions(id) ON DELETE CASCADE,
    action           TEXT NOT NULL CHECK (action IN ('DEPLOYMENT','ROLLBACK')),
    status           TEXT NOT NULL CHECK (status IN ('SUCCESS','FAILED')),
    deployed_by      TEXT NOT NULL,
    deployment_time  TEXT NOT NULL,
    notes            TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rollbacks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id      INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    from_version  INTEGER NOT NULL,
    to_version    INTEGER NOT NULL,
    performed_by  TEXT NOT NULL,
    rollback_time TEXT NOT NULL,
    reason        TEXT DEFAULT ''
);
"""


def init_db() -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_conn():
    """Open a connection; commit on success, roll back on any error."""
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
