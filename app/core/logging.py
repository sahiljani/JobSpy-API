import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_file = Path(settings.log_file_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
