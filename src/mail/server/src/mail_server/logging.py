# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import logging
from datetime import datetime
from pathlib import Path


def init_logger() -> Path:
    """
    Initialize the logger for mail-server.
    """

    today_str = datetime.today().strftime("%Y_%m_%d")
    log_filepath = Path.home().joinpath(
        ".mail-swarms", "server_logs", f"{today_str}.log"
    )
    log_filepath.parent.mkdir(parents=True, exist_ok=True)

    # formatter
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # file handler
    file_handler = logging.FileHandler(
        filename=log_filepath,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, stream_handler],
        force=True,
    )

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.setLevel(logging.INFO)
        uvicorn_logger.propagate = True

    logger = logging.getLogger(__name__)
    logger.info("logger setup complete")

    return log_filepath
