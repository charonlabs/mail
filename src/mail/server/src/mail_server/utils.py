# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from importlib import metadata


def get_version() -> str:
    """
    Get the current version of mail-server.
    """
    try:
        return metadata.version("mail-server")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def get_user_agent() -> str:
    """
    Get the MAIL swarm `User-Agent` header.
    """
    return f"MAIL-Swarm/{get_version()} (https://github.com/charonlabs/mail)"
