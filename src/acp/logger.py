import logging
import os
from datetime import datetime

from rich.logging import RichHandler


def get_loggers():
    """
    Get the loggers for the application.
    """
    return list(logging.root.manager.loggerDict.keys())


def init_logger():
    """
    Initialize the logger for the application.
    """
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # File handler
    file_handler = logging.FileHandler(
        f"logs/acp_{datetime.now().strftime('%Y-%m-%d')}.log"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] - %(message)s")
    )

    # for all loggers that are not acp, clear all handlers
    # and then add only the file handler above
    for logger in get_loggers():
        if not logger.startswith("acp"):
            logging.getLogger(logger).propagate = False
            logging.getLogger(logger).handlers.clear()
            logging.getLogger(logger).addHandler(file_handler)

    # Rich handler for colored console output
    console_handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_level=True,
        show_path=False,
    )
    console_handler.setLevel(logging.DEBUG)

    # Configure the charon logger (using the actual module name)
    charon_logger = logging.getLogger("acp")
    charon_logger.setLevel(logging.DEBUG)
    charon_logger.propagate = False  # Prevent double logging

    # Clear any existing handlers
    charon_logger.handlers.clear()

    # Add our handlers
    charon_logger.addHandler(console_handler)
    charon_logger.addHandler(file_handler)

    # Configure root logger to avoid conflicts with Uvicorn
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Only add file handler to root if it doesn't already have handlers
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
