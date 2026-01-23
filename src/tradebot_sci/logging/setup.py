from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from tradebot_sci.config.models import LoggingSettings


def setup_logging(settings: LoggingSettings) -> None:
    log_dir = Path(settings.file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    level = getattr(logging, settings.level.upper(), logging.INFO)

    file_handler = RotatingFileHandler(
        settings.file,
        maxBytes=settings.max_bytes,
        backupCount=settings.backup_count,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(level)

    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("parso").setLevel(logging.WARNING)

    # Suppress noisy libraries
