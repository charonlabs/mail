# SPDX-Licence-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import argparse

from mail_daemon.logger import init_logger
from mail_daemon.maild.api import run_daemon


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mail-daemon",
        usage="mail-daemon [option]...",
        description="Multi-Agent Interface Layer (MAIL) daemon implementation in Python",
        epilog="Copyright (c) 2026 Addison Kline",
    )
    parser.add_argument(
        "-llf",
        "-log-level-file",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="the minimum log level to write to the daemon log file (default: %(default)s)",
    )
    parser.add_argument(
        "-llc",
        "--log-level-console",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="the minimum log level to write to the console (default: %(default)s)",
    )

    # parse and handle args
    args = parser.parse_args()

    init_logger(log_level_file=args.llf, log_level_console=args.log_level_console)

    try:
        run_daemon(args)
    except Exception as e:
        print(f"run_daemon failed: {e}")
        exit(1)
