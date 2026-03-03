# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from toml import load as load_toml


def get_version() -> str:
    """
    Get the current version of the MAIL reference implementation.
    """
    return load_toml("pyproject.toml")["project"]["version"]


def get_protocol_version() -> str:
    """
    Get the current protocol version of the MAIL reference implementation.
    If the ref-impl version is `x.y.z`, the protocol version is `x.y`.
    """
    version = load_toml("pyproject.toml")["project"]["version"]
    return f"{version.split('.')[0]}.{version.split('.')[1]}"
