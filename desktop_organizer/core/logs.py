"""A small rotating log file, so problems can be diagnosed after the fact."""

from __future__ import annotations

import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from desktop_organizer import __version__
from desktop_organizer.core.paths import app_data_dir

LOGGER_NAME = "desktop_organizer"
log = logging.getLogger(LOGGER_NAME)


def log_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file() -> Path:
    return log_dir() / "desktop-organizer.log"


def setup_logging(level: int = logging.INFO) -> Path:
    """Send this app's log messages to a 1 MB file, keeping 3 old copies."""
    path = log_file()
    if not any(isinstance(h, RotatingFileHandler) for h in log.handlers):
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        log.addHandler(handler)
    log.setLevel(level)
    log.propagate = False
    log.info("Desktop Organizer %s starting (Python %s, %s)", __version__,
             platform.python_version(), platform.platform())
    return path


def describe_environment() -> str:
    """Details worth including when someone reports a problem."""
    frozen = "installed app" if getattr(sys, "frozen", False) else "from source"
    return f"Desktop Organizer {__version__} ({frozen}), Python {platform.python_version()}, {platform.platform()}"
