"""Application logging with timestamps (console + logs/app.log)."""
import logging
import os
from pathlib import Path


def _setup() -> logging.Logger:
    logger = logging.getLogger("mvs")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    try:
        log_dir = Path(os.getenv("MVS_LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "app.log")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        pass
    return logger


log = _setup()
