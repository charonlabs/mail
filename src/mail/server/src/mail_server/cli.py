# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import argparse

from mail_protocol.constants import MAIL_DEFAULT_HOST, MAIL_DEFAULT_PORT

from mail_server.server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mail-server",
        usage="mail-server [option]...",
        description="The Python/FastAPI server for the Multi-Agent Interface Layer (MAIL)",
        epilog="Copyright (c) 2026 Addison Kline",
    )
    parser.add_argument(
        "-H",
        "--host",
        default=MAIL_DEFAULT_HOST,
        help="the IP address to bind to (default: %(default)s)",
    )
    parser.add_argument(
        "-p",
        "--port",
        default=MAIL_DEFAULT_PORT,
        type=int,
        help="the port for the server to listen on (default: %(default)s)",
    )
    parser.add_argument(
        "-b",
        "--backend",
        choices=["memory"],
        default="memory",
        help="the MAIL server backend to use (default: %(default)s)",
    )

    # parse and handle args
    args = parser.parse_args()

    run_server(args)
