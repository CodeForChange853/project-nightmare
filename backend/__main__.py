"""Run with:  python -m backend   (always binds to 127.0.0.1).

Safe to run under both `python.exe` (interactive terminal) and `pythonw.exe`
(windowless Task Scheduler auto-start), logging to `backend/logs/nightmare.log`.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

import uvicorn

from .config import BACKEND_DIR, Settings
from .main import create_app

LOG_DIR = BACKEND_DIR / "logs"


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "nightmare.log"
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    ]
    if sys.stdout is not None and hasattr(sys.stdout, "write"):
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def main() -> None:
    configure_logging()
    log = logging.getLogger("nightmare")
    settings = Settings.from_env()
    log.info("Starting Project Nightmare on http://127.0.0.1:%s", settings.port)
    app = create_app(settings=settings)
    uvicorn.run(app, host="127.0.0.1", port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
