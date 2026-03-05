# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from importlib import metadata


def get_version() -> str:
    """
    Get the current version of mail-server.
    """
    version = metadata.version("mail-server")
    return version


def get_user_agent() -> str:
    """
    Get the MAIL swarm `User-Agent` header.
    """
    return f"MAIL-Swarm/{get_version()} (https://github.com/charonlabs/mail)"