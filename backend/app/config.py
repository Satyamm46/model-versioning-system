"""Central configuration. Everything is read from environment variables at call time,
so tests and Jenkins can redirect the database / storage paths without code changes."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
APP_NAME = "Model Versioning System"
ALLOWED_EXTENSIONS = {".pkl", ".joblib"}
VALID_STATUSES = ("DRAFT", "TESTING", "STAGING", "PRODUCTION", "ARCHIVED", "FAILED")


def db_path() -> Path:
    return Path(os.getenv("MVS_DB_PATH", BASE_DIR / "mvs.db"))


def storage_dir() -> Path:
    """Where every uploaded version lives: <storage>/<model-slug>/v<N>/model.pkl"""
    return Path(os.getenv("MVS_MODEL_DIR", BASE_DIR / "models"))


def deploy_dir() -> Path:
    """Where the PRODUCTION copy of each model is published."""
    return Path(os.getenv("MVS_DEPLOY_DIR", BASE_DIR / "deployed"))


def max_upload_bytes() -> int:
    return int(float(os.getenv("MVS_MAX_UPLOAD_MB", "50")) * 1024 * 1024)
