"""Logging configuration for Mini-RAG."""
import logging
import logging.config
from typing import Any, Dict

from app.config import LOG_DIR, LOG_LEVEL


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def build_log_config() -> Dict[str, Any]:
    _ensure_log_dir()
    app_log = str(LOG_DIR / "app.log")
    access_log = str(LOG_DIR / "access.log")

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            },
            "access": {
                "format": "%(asctime)s | %(levelname)s | %(name)s | %(client_addr)s - \"%(request_line)s\" %(status_code)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": LOG_LEVEL,
                "formatter": "default",
            },
            "app_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "default",
                "filename": app_log,
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "access_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "access",
                "filename": access_log,
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "": {
                "handlers": ["console", "app_file"],
                "level": LOG_LEVEL,
            },
            "uvicorn.error": {
                "handlers": ["console", "app_file"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console", "access_file"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
        },
    }


def configure_logging() -> Dict[str, Any]:
    config = build_log_config()
    logging.config.dictConfig(config)
    return config
