# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import argparse
import asyncio
import os
from pathlib import Path

from mail import utils
from mail.client import MAILClientCLI
from mail.config import ClientConfig, ServerConfig
from mail.server import run_server


def _str_to_bool(value: str | bool) -> bool:
    """
    Parse common string representations of booleans.
    """

    if isinstance(value, bool):
        return value

    normalized = value.lower()
    if normalized in {"true", "t", "1", "yes", "y"}:
        return True
    if normalized in {"false", "f", "0", "no", "n"}:
        return False

    raise argparse.ArgumentTypeError(
        f"invalid boolean value '{value}'; expected true/false"
    )


def _run_server_with_args(args: argparse.Namespace) -> None:
    """
    Run a MAIL server with the given CLI args.
    Given CLI args will override the defaults in the config file.
    """
    original_config_path = os.environ.get("MAIL_CONFIG_PATH")
    env_overridden = False

    try:
        if args.config:
            resolved_config = Path(args.config).expanduser().resolve()
            os.environ["MAIL_CONFIG_PATH"] = str(resolved_config)
            env_overridden = True

        base_config = ServerConfig()

        server_overrides: dict[str, object] = {}
        if args.host is not None:
            server_overrides["host"] = args.host
        if args.port is not None:
            server_overrides["port"] = args.port
        if args.reload is not None:
            server_overrides["reload"] = args.reload
        if args.debug is not None:
            server_overrides["debug"] = args.debug

        swarm_overrides: dict[str, object] = {}
        if args.swarm_name is not None:
            swarm_overrides["name"] = args.swarm_name
        if args.swarm_source is not None:
            swarm_overrides["source"] = args.swarm_source
        if args.swarm_registry is not None:
            swarm_overrides["registry_file"] = args.swarm_registry

        if swarm_overrides:
            server_overrides["swarm"] = base_config.swarm.model_copy(
                update=swarm_overrides
            )

        effective_config = (
            base_config.model_copy(update=server_overrides)
            if server_overrides
            else base_config
        )

        run_server(cfg=effective_config)
    finally:
        if env_overridden:
            if original_config_path is None:
                os.environ.pop("MAIL_CONFIG_PATH", None)
            else:
                os.environ["MAIL_CONFIG_PATH"] = original_config_path


def _run_client_with_args(args: argparse.Namespace) -> None:
    """
    Run a MAIL client with the given CLI args.
    """
    original_config_path = os.environ.get("MAIL_CONFIG_PATH")
    env_overridden = False

    try:
        if args.config:
            resolved_config = Path(args.config).expanduser().resolve()
            os.environ["MAIL_CONFIG_PATH"] = str(resolved_config)
            env_overridden = True

        client_config = ClientConfig()
        if args.timeout is not None:
            client_config.timeout = args.timeout

        if args.verbose:
            client_config.verbose = True

        client_cli = MAILClientCLI(args, config=client_config)
        asyncio.run(client_cli.run())
    finally:
        if env_overridden:
            if original_config_path is None:
                os.environ.pop("MAIL_CONFIG_PATH", None)
            else:
                os.environ["MAIL_CONFIG_PATH"] = original_config_path


def _print_version(_args: argparse.Namespace) -> None:
    """
    Print the version of MAIL.
    """
    print(f"MAIL reference implementation version: {utils.get_version()}")
    print(f"MAIL protocol version: {utils.get_protocol_version()}")
    print(
        "For a given MAIL reference implementation with version `x.y.z`, the protocol version is `x.y`"
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
        "-c",
        "--config",
        type=str,
        required=False,
        help="path to the MAIL configuration file",
    )
    server_parser.add_argument(
        "-p",
        "--port",
        type=int,
        required=False,
        help="port to listen on",
    )
    server_parser.add_argument(
        "-H",
        "--host",
        type=str,
        required=False,
        help="host to listen on",
    )
    server_parser.add_argument(
        "-r",
        "--reload",
        action="store_true",
        help="enable hot reloading",
    )
    server_parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="enable debug mode (enable optional endpoints)",
    )
    server_parser.add_argument(
        "-n",
        "--swarm-name",
        type=str,
        required=False,
        help="name of the swarm",
    )
    server_parser.add_argument(
        "-s",
        "--swarm-source",
        type=str,
        required=False,
        help="source of the swarm",
    )
    server_parser.add_argument(
        "-rf",
        "--swarm-registry",
        type=str,
        required=False,
        help="registry file of the swarm",
    )

    # command `client`
    client_parser = subparsers.add_parser("client", help="run the MAIL client")
    client_parser.set_defaults(func=_run_client_with_args)
    client_parser.add_argument(
        "-c",
        "--config",
        type=str,
        required=False,
        help="path to the MAIL configuration file",
    )
    client_parser.add_argument(
        "url",
        type=str,
        help="URL of the MAIL server",
    )
    client_parser.add_argument(
        "-ak",
        "--api-key",
        type=str,
        required=False,
        help="API key for the MAIL server",
    )
    client_parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        required=False,
        help="client request timeout time in seconds",
    )
    client_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable verbose output",
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
