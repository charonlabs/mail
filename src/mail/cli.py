# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import argparse
import asyncio

from mail.client import MAILClientCLI
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


def _run_client_with_args(args: argparse.Namespace) -> None:
    """
    Run a MAIL client with the given CLI args.
    """
    client_cli = MAILClientCLI(args)
    asyncio.run(client_cli.run())


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

    # command `client`
    client_parser = subparsers.add_parser("client", help="run the MAIL client")
    client_parser.set_defaults(func=_run_client_with_args)
    client_parser.add_argument(
        "--config",
        default="mail.toml",
    )
    client_parser.add_argument(
        "--url",
        type=str,
        help="URL of the MAIL server",
    )
    client_parser.add_argument(
        "--api-key",
        type=str,
        required=False,
        help="API key for the MAIL server",
    )
    client_parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="timeout for the MAIL server",
    )
    
    # parse CLI args
    args = parser.parse_args()

    # if no command is provided, print the help
    if not hasattr(args, "func"):
        parser.print_help()
        return

    # run the command
    args.func(args)


if __name__ == "__main__":
    main()