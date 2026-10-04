"""Model file validation: exists? extension ok? size ok? can it be loaded?

SECURITY NOTE: .pkl/.joblib files are Python pickles and loading one can run code.
To keep the API process safe we load the file in a separate short-lived Python
process with a timeout, and we never load files that fail the extension/size checks.
In a real system you would also only accept models from trusted users."""
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from backend.app.config import ALLOWED_EXTENSIONS, max_upload_bytes

LOAD_TIMEOUT_SECONDS = 60
_LOADER = "import sys, joblib; joblib.load(sys.argv[1])"


def has_valid_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def validate_model_file(path) -> Tuple[bool, str]:
    p = Path(path)
    if not p.is_file():
        return False, "File does not exist"
    if not has_valid_extension(p.name):
        return False, "Invalid file extension (allowed: .pkl, .joblib)"
    size = p.stat().st_size
    if size == 0:
        return False, "File is empty"
    if size > max_upload_bytes():
        return False, "File exceeds the maximum allowed size"
    try:
        result = subprocess.run(
            [sys.executable, "-c", _LOADER, str(p)],
            capture_output=True, text=True, timeout=LOAD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, "Model loading timed out"
    if result.returncode != 0:
        return False, "Model could not be loaded with joblib (corrupt or incompatible file)"
    return True, "Validation passed: file exists, extension and size OK, model loads"
