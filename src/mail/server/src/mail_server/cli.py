# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import argparse
import os

from mail_protocol.cli_help import make_arg_parser
from mail_protocol.constants import MAIL_DEFAULT_HOST, MAIL_DEFAULT_PORT

EXAMPLES = [
    "mail-server",
    "mail-server --host 0.0.0.0 --port 8865",
    "mail-server --backend memory",
    "mail-server --memory-save-interval 30",
    "mail-server --backend sqlite",
    "mail-server --backend sqlite --sqlite-path /var/lib/mail/mail.db",
    "mail-server --backend sqlite --database-url sqlite:////abs/path/mail.db",
]

DEFAULT_MEMORY_SAVE_INTERVAL_SECONDS = 60.0


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _default_memory_save_interval() -> float:
    raw_value = os.getenv("MAIL_MEMORY_SAVE_INTERVAL_SECONDS")
    if raw_value is None:
        return DEFAULT_MEMORY_SAVE_INTERVAL_SECONDS
    return _non_negative_float(raw_value)


def build_parser() -> argparse.ArgumentParser:
    parser = make_arg_parser(
        prog="mail-server",
        usage="mail-server [option]...",
        description="The Python/FastAPI server for the Multi-Agent Interface Layer (MAIL)",
        examples=EXAMPLES,
    )
    parser.add_argument(
        "-H",
        "--host",
        metavar="HOST",
        default=MAIL_DEFAULT_HOST,
        help="the IP address to bind to (default: %(default)s)",
    )
    parser.add_argument(
        "-p",
        "--port",
        metavar="PORT",
        default=MAIL_DEFAULT_PORT,
        type=int,
        help="the port for the server to listen on (default: %(default)s)",
    )
    parser.add_argument(
        "-b",
        "--backend",
        metavar="BACKEND",
        choices=["memory", "sqlite"],
        default="memory",
        help="the MAIL server backend to use (default: %(default)s)",
    )
    parser.add_argument(
        "--memory-save-interval",
        metavar="SECONDS",
        default=_default_memory_save_interval(),
        type=_non_negative_float,
        help=(
            "seconds between memory backend filesystem checkpoints; "
            "set 0 to disable (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--sqlite-path",
        metavar="PATH",
        default=os.getenv("MAIL_SQLITE_PATH"),
        help=(
            "sqlite backend database file (env: MAIL_SQLITE_PATH; default: "
            "~/.mail-swarms/deployments/default/mail.db)"
        ),
    )
    parser.add_argument(
        "--database-url",
        metavar="URL",
        default=os.getenv("MAIL_DATABASE_URL"),
        help=(
            "sqlite backend database URL; takes precedence over --sqlite-path "
            "(env: MAIL_DATABASE_URL)"
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    from mail_server.server import run_server

    run_server(args)
