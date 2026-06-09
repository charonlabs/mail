# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import argparse

from mail_protocol.cli_help import make_arg_parser
from mail_protocol.constants import MAIL_DEFAULT_HOST, MAIL_DEFAULT_PORT

EXAMPLES = [
    "mail-server",
    "mail-server --host 0.0.0.0 --port 8865",
    "mail-server --backend memory",
]


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
        choices=["memory"],
        default="memory",
        help="the MAIL server backend to use (default: %(default)s)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    from mail_server.server import run_server

    run_server(args)
