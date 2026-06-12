# SPDX-Licence-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import logging
from datetime import datetime
from pathlib import Path


def init_logger(
    log_level_file: str,
    log_level_console: str,
) -> None:
    """
    Initialize the logger for mail-daemon.
    """

    llf_upper = log_level_file.upper()
    match llf_upper:
        case "DEBUG":
            llf = logging.DEBUG
        case "INFO":
            llf = logging.INFO
        case "WARNING":
            llf = logging.WARNING
        case "ERROR":
            llf = logging.ERROR
        case "CRITICAL":
            llf = logging.CRITICAL
        case _:
            raise ValueError(f"invalid log_level_file: {log_level_file}")

    llc_upper = log_level_console.upper()
    match llc_upper:
        case "DEBUG":
            llc = logging.DEBUG
        case "INFO":
            llc = logging.INFO
        case "WARNING":
            llc = logging.WARNING
        case "ERROR":
            llc = logging.ERROR
        case "CRITICAL":
            llc = logging.CRITICAL
        case _:
            raise ValueError(f"invalid log_level_console: {log_level_console}")

    today_str = datetime.today().strftime("%Y_%m_%d")
    log_filepath = Path.home().joinpath(
        ".mail-swarms",
        "daemon_logs",
        f"{today_str}.log",
    )
    log_filepath.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # file handler
    file_handler = logging.FileHandler(log_filepath)
    file_handler.setLevel(llf)
    file_handler.setFormatter(formatter)

    # stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(llc)
    stream_handler.setFormatter(formatter)

    logging.basicConfig(
        handlers=[file_handler, stream_handler], level=min(llf, llc), force=True
    )

    logger = logging.getLogger()
    logger.info("logger initialized")
