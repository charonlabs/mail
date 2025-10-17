# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import logging
import os

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
        f"logs/mail_{datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d')}.log"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] :: %(message)s")
    )

    # for all loggers that are not mail, clear all handlers
    # and then add only the file handler above
    for logger in get_loggers():
        if not logger.startswith("mail"):
            logging.getLogger(logger).propagate = False
            logging.getLogger(logger).handlers.clear()
            logging.getLogger(logger).addHandler(file_handler)

    # Rich handler for colored console output
    # All `mail.*` loggers should use this handler
    # Use `mailquiet.*` for loggers that should not be verbose
    console_handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_level=True,
        show_path=True,
        markup=True,
        tracebacks_show_locals=True,
    )
    console_handler.setLevel(logging.DEBUG)

    # Configure the mail logger (using the actual module name)
    mail_logger = logging.getLogger("mail")
    mail_logger.setLevel(logging.DEBUG)
    mail_logger.propagate = False  # Prevent double logging

    # Clear any existing handlers
    mail_logger.handlers.clear()

    # Add our handlers
    mail_logger.addHandler(console_handler)
    mail_logger.addHandler(file_handler)

    # Configure root logger to avoid conflicts with Uvicorn
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Only add file handler to root if it doesn't already have handlers
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
