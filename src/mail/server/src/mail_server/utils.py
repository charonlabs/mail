# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from importlib import metadata
from typing import Any

from mail_protocol.network.requests import BoxFilterParams


def build_box_metadata(
    filters: BoxFilterParams, total: int, returned: int
) -> dict[str, Any]:
    """
    Build the `metadata` block returned by the "GET box" endpoints, echoing
    the applied filters alongside the pagination counts so clients can page.
    """

    return {
        "total": total,
        "returned": returned,
        "limit": filters.limit,
        "offset": filters.offset,
        "sort_by": filters.sort_by,
        "order": filters.order,
    }


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
