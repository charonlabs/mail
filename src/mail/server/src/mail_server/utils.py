# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from importlib import metadata


def get_mail_server_version() -> str:
    """
    Get the version of `mail-server` from package metadata.
    """

    version = metadata.version("mail-server")
    return version


def get_mail_protocol_version() -> str:
    """
    Get the version of the MAIL protocol being used by `mail-server`.
    """

    mail_server_v = get_mail_server_version()
    major, minor, _patch = mail_server_v.split(".")
    return f"{major}.{minor}"
