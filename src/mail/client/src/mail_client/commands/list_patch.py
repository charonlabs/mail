# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.requests import AdminListPatchRequest
from mail_protocol.network.responses import (
    AdminListPatchResponse,
)
from pydantic import ValidationError


def cmd_list_patch(args: Namespace) -> None:
    """
    Update an existing mailing list on the MAIL server.
    """

    raise NotImplementedError
