"""CD step: deploy the zip made by build.py.

  python scripts/deploy.py             -> unpack new release, (re)start the app on it
  python scripts/deploy.py --rollback  -> switch back to the previous release

Layout under DEPLOY_ROOT (default: <project>/deploy_target):
  releases/<version>/   one folder per release (old ones are kept => easy rollback)
  current.txt           name of the live release
  previous.txt          name of the release that was live before
  data/                 database + model files (shared by all releases, survives deploys)
  deployment_history.json
"""
import json
import os
import signal
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ROOT = Path(os.getenv("DEPLOY_ROOT", ROOT / "deploy_target"))
PORT = os.getenv("MVS_PORT", "8000")


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(version: str, status: str, note: str = "") -> None:
    hist_file = DEPLOY_ROOT / "deployment_history.json"
    history = json.loads(hist_file.read_text()) if hist_file.exists() else []
    history.append({"version": version, "status": status, "time": stamp(), "note": note})
    hist_file.write_text(json.dumps(history, indent=2))


def stop_running() -> None:
    pid_file = DEPLOY_ROOT / "app.pid"
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text())
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"Stopped previous application (pid {pid})")
    except (ProcessLookupError, ValueError, PermissionError):
        pass
    pid_file.unlink(missing_ok=True)


def start(release_dir: Path) -> None:
    data = DEPLOY_ROOT / "data"
    data.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ,
               MVS_DB_PATH=str(data / "mvs.db"),
               MVS_MODEL_DIR=str(data / "models"),
               MVS_DEPLOY_DIR=str(data / "deployed"),
               MVS_LOG_DIR=str(data / "logs"))
    log = open(DEPLOY_ROOT / "app.out.log", "ab")
    kwargs = {"creationflags": 0x00000008} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app",
                             "--host", "0.0.0.0", "--port", PORT],
                            cwd=release_dir, env=env, stdout=log, stderr=log, **kwargs)
    (DEPLOY_ROOT / "app.pid").write_text(str(proc.pid))
    print(f"Application started from {release_dir.name} on port {PORT} (pid {proc.pid})")


def read(name: str):
    f = DEPLOY_ROOT / name
    return f.read_text().strip() if f.exists() else None


def main() -> int:
    DEPLOY_ROOT.mkdir(parents=True, exist_ok=True)

    if "--rollback" in sys.argv:
        target = read("previous.txt")
        if not target:
            print("No previous release to roll back to")
            return 1
        failed = read("current.txt")
        stop_running()
        start(DEPLOY_ROOT / "releases" / target)
        (DEPLOY_ROOT / "current.txt").write_text(target)
        (DEPLOY_ROOT / "previous.txt").write_text(failed or target)
        record(target, "ROLLBACK", f"rolled back from {failed}")
        return 0

    latest = ROOT / "dist" / "LATEST"
    if not latest.exists():
        print("Nothing to deploy: run scripts/build.py first")
        return 1
    archive = ROOT / "dist" / latest.read_text().strip()
    version = archive.stem.replace("model-versioning-system-", "")
    release_dir = DEPLOY_ROOT / "releases" / version
    try:
        with zipfile.ZipFile(archive) as z:
            z.extractall(release_dir)
        current = read("current.txt")
        stop_running()
        start(release_dir)
        if current:
            (DEPLOY_ROOT / "previous.txt").write_text(current)
        (DEPLOY_ROOT / "current.txt").write_text(version)
        record(version, "SUCCESS")
        print(f"Deployment of {version} completed")
        return 0
    except Exception as exc:  # any failure -> history says FAILED, Jenkins stage fails
        record(version, "FAILED", str(exc))
        print(f"Deployment failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
