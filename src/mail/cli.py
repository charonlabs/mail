# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import argparse
import asyncio

from mail import utils
from mail.client import MAILClientCLI
from mail.config.server import ServerConfig, SwarmConfig
from mail.server import run_server


def _run_server_with_args(args: argparse.Namespace) -> None:
    """
    Run a MAIL server with the given CLI args.
    Given CLI args will override the defaults in the config file.
    """
    run_server(
        cfg=ServerConfig(),
    )


def _run_client_with_args(args: argparse.Namespace) -> None:
    """
    Run a MAIL client with the given CLI args.
    """
    client_cli = MAILClientCLI(args)
    asyncio.run(client_cli.run())


def _print_version(_args: argparse.Namespace) -> None:
    """
    Print the version of MAIL.
    """
    print(f"MAIL reference implementation version: {utils.get_version()}")
    print(f"MAIL protocol version: {utils.get_protocol_version()}")
    print("For a given MAIL reference implementation with version `x.y.z`, the protocol version is `x.y`")


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
        type=str,
        required=False,
        help="path to the MAIL configuration file",
    )
    server_parser.add_argument(
        "--port",
        type=int,
        required=False,
        help="port to listen on",
    )
    server_parser.add_argument(
        "--host", 
        type=str,
        required=False,
        help="host to listen on",
    )
    server_parser.add_argument(
        "--reload",
        type=bool,
        required=False,
        help="enable hot reloading",
    )
    server_parser.add_argument(
        "--swarm-name",
        type=str,
        required=False,
        help="name of the swarm",
    )
    server_parser.add_argument(
        "--swarm-source",
        type=str,
        required=False,
        help="source of the swarm",
    )
    server_parser.add_argument(
        "--swarm-registry",
        type=str,
        required=False,
        help="registry file of the swarm",
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
        default=3600.0,
        help="timeout for the MAIL server",
    )

    # command `version`
    version_parser = subparsers.add_parser("version", help="print the version of MAIL")
    version_parser.set_defaults(func=_print_version)
    
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