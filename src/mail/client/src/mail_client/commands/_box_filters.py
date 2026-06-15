# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from argparse import Namespace


def box_filter_params(args: Namespace) -> dict[str, str | int]:
    """
    Collect the shared "GET box" query-param flags (``--limit``, ``--offset``,
    ``--sort-by``, ``--order``) from parsed CLI args, omitting any left unset
    so the server applies its own defaults.
    """

    params: dict[str, str | int] = {}
    for flag in ("limit", "offset", "sort_by", "order"):
        value = getattr(args, flag, None)
        if value is not None:
            params[flag] = value
    return params
