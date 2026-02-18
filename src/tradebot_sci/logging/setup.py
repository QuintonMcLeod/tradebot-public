from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from tradebot_sci.config.models import LoggingSettings  # noqa: I001


def _make_json_formatter() -> logging.Formatter:
    """Create a JSON formatter for machine-parseable structured logging.

    Uses python-json-logger if available, otherwise falls back to a
    simple JSON-like line format.
    """
    try:
        from pythonjsonlogger.json import JsonFormatter

        return JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
    except ImportError:
        # Fallback: structured-ish format if python-json-logger not installed
        return logging.Formatter(
            fmt='{"timestamp":"%(asctime)s","level":"%(levelname)s",'
                '"logger":"%(name)s","message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )


def setup_logging(settings: LoggingSettings) -> None:
    log_dir = Path(settings.file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Human-readable format for console
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Structured JSON format for file (machine-parseable, alertable)
    json_formatter = _make_json_formatter()

    level = getattr(logging, settings.level.upper(), logging.INFO)

    file_handler = RotatingFileHandler(
        settings.file,
        maxBytes=settings.max_bytes,
        backupCount=settings.backup_count,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(json_formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)

    logger = logging.getLogger()
    logger.setLevel(level)

    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("parso").setLevel(logging.WARNING)

