"""CI step: package the application into dist/model-versioning-system-<version>.zip.
The version comes from RELEASE_VERSION (set by the Jenkins 'Version Generation' stage)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def main() -> int:
    version = os.getenv("RELEASE_VERSION", "1.0.0-local")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "release"
        stage.mkdir()
        shutil.copytree(ROOT / "backend", stage / "backend", ignore=IGNORE)
        shutil.copytree(ROOT / "frontend", stage / "frontend", ignore=IGNORE)
        shutil.copy2(ROOT / "requirements.txt", stage / "requirements.txt")
        info = {"version": version, "git_commit": git_sha(),
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (stage / "build_info.json").write_text(json.dumps(info, indent=2))
        archive = shutil.make_archive(str(dist / f"model-versioning-system-{version}"), "zip", stage)

    (dist / "LATEST").write_text(Path(archive).name)
    print(f"Build created: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
