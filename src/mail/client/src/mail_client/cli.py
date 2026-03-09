# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import argparse

from mail_client.utils import print_version

from .client import run_client


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="newman",
        usage="newman [options] <command> [arguments]",
        description="A CLI-based REPL client for the MAIL protocol.",
        epilog="Copyright (c) 2026 Addison Kline and the MAIL contributors" \
             " (https://github.com/charonlabs/mail)"
    )
    subparsers = parser.add_subparsers(title="commands", dest="command")

    # command `connect` (connect to a MAIL server)
    connect_desc = "Connect to a MAIL server"
    connect_p = subparsers.add_parser(
        "connect",
        usage="newman connect <url> [options]",
        aliases=["c"],
        help=connect_desc,
        description=connect_desc,
    )
    connect_p.add_argument(
        "url",
        type=str,
        help="The URL of the MAIL server to connect to",
    )
    connect_p.set_defaults(func=run_client)

    # command `version` (print the version of NEWMAN and the MAIL protocol)
    version_desc = "Print the version of NEWMAN and the MAIL protocol"
    version_p = subparsers.add_parser(
        "version",
        usage="newman version [options]",
        aliases=["V"],
        help=version_desc,
        description=version_desc,
    )
    version_p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Include more detailed software information",
    )
    version_p.set_defaults(func=print_version)

    args = parser.parse_args()

    try:
        args.func(args)
    except AttributeError:
        parser.print_usage()
        print("for help, run `newman -h`/`newman --help`")
        exit(1)