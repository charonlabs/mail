# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import argparse

from mail.server import run_server


def _run_server_with_args(args: argparse.Namespace) -> None:
    """
    Run a MAIL server with the given CLI args.
    """
    run_server(
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def main() -> None:
    # top-level MAIL parser
    parser = argparse.ArgumentParser(
        prog="mail",
        description="Multi-Agent Interface Layer reference implementation CLI",
        epilog="For more information, see `README.md` and `docs/`",
    )
    
    # subparsers for each MAIL command
    subparsers = parser.add_subparsers()

    # command `server`
    server_parser = subparsers.add_parser("server", help="start the MAIL server")
    server_parser.set_defaults(func=_run_server_with_args)
    server_parser.add_argument(
        "--config",
        default="mail.toml",
        type=str, 
        help="path to the MAIL configuration file",
    )
    server_parser.add_argument(
        "--port",
        default=8000,
        type=int, 
        help="port to listen on",
    )
    server_parser.add_argument(
        "--host", 
        default="0.0.0.0",
        type=str, 
        help="host to listen on",
    )
    server_parser.add_argument(
        "--reload",
        default=False,
        type=bool,
        help="enable hot reloading",
    )
    
    # parse CLI args
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()