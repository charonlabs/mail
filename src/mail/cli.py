# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import argparse


def main() -> None:
    # top-level MAIL parser
    parser = argparse.ArgumentParser(
        prog="mail",
        description="Multi-Agent Interface Layer reference implementation",
        epilog="For more information, see `README.md` and `docs/`",
    )
    
    # subparsers for each MAIL command
    subparsers = parser.add_subparsers(help="sub-command help")

    # command `server`
    server_parser = subparsers.add_parser("server", help="start the MAIL server")
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
        "--debug",
        action="store_true", 
        help="enable debug mode",
    )
    


if __name__ == "__main__":
    main()