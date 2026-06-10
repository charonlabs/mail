# SPDX-Licence-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import argparse

from mail_protocol.cli_help import make_arg_parser

from mail_daemon.logger import init_logger
from mail_daemon.maild.api import run_daemon

EXAMPLES = [
    "mail-daemon",
    "mail-daemon --log-level-console debug",
    "mail-daemon --log-level-file warning",
]


def build_parser() -> argparse.ArgumentParser:
    parser = make_arg_parser(
        prog="mail-daemon",
        usage="mail-daemon [option]...",
        description="Multi-Agent Interface Layer (MAIL) daemon implementation in Python",
        examples=EXAMPLES,
    )
    parser.add_argument(
        "-llf",
        "--log-level-file",
        metavar="LEVEL",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="file log level (default: %(default)s)",
    )
    parser.add_argument(
        "-llc",
        "--log-level-console",
        metavar="LEVEL",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="console log level (default: %(default)s)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    init_logger(
        log_level_file=args.log_level_file, log_level_console=args.log_level_console
    )

    try:
        run_daemon(args)
    except Exception as e:
        print(f"run_daemon failed: {e}")
        exit(1)
