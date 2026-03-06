# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from importlib import metadata


def get_version() -> str:
    """
    Get the current version of mail-client.
    """
    version = metadata.version("mail-client")
    return version