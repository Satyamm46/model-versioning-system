"""CI step: validate the app imports and every model file stored in the repo's models/ folder.
Exit code 1 (=> Jenkins stage FAILS => no deployment) if anything is invalid."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.config import ALLOWED_EXTENSIONS  # noqa: E402
from backend.services.validation import validate_model_file  # noqa: E402


def main() -> int:
    importlib.import_module("backend.main")  # fails if the app cannot even be imported
    print("Application imports correctly")

    folder = ROOT / "models"
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in ALLOWED_EXTENSIONS)
    if not files:
        print("No model files in models/ - nothing to validate")
        return 0

    failed = 0
    for f in files:
        ok, msg = validate_model_file(f)
        print(f"[{'OK' if ok else 'FAIL'}] {f.relative_to(ROOT)} - {msg}")
        failed += not ok
    if failed:
        print(f"Model validation FAILED for {failed} file(s)")
        return 1
    print(f"All {len(files)} model file(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
