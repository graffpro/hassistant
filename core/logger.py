"""
Structured logger for UE5 AI Assistant.
"""
import sys
from pathlib import Path
from loguru import logger

from core.config import LOGS_DIR


def setup_logger(debug: bool = False) -> None:
    logger.remove()

    level = "DEBUG" if debug else "INFO"

    # Console output
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # File output (rotating)
    logger.add(
        LOGS_DIR / "assistant_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    logger.info("Logger initialized")


__all__ = ["logger", "setup_logger"]
