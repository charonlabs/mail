# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from argparse import Namespace
from importlib import metadata


def get_version() -> str:
    """
    Get the current version of mail-client.
    """
    version = metadata.version("mail-client")
    return version


def get_protocol_version() -> str:
    """
    Get the current protocol version of the MAIL protocol.
    """
    version = metadata.version("mail-protocol")
    return version


def print_version(args: Namespace) -> None:
    """
    Print the version of mail-client.
    """
    print(f"NEWMAN version: {get_version()}")
    print(f"MAIL protocol version: {get_protocol_version()}")
    
    if args.verbose:
        print()
        print("Created by Addison Kline the MAIL contributors")
        print("  Repository: https://github.com/charonlabs/mail")
        print("  Website: https://charon-labs.com")
        print("License: Apache-2.0")
        print("  See `LICENSE` in the project root")