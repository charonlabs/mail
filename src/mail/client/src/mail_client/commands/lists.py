# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.responses import (
    ListsGetResponse,
)
from pydantic import ValidationError


def cmd_lists(args: Namespace) -> None:
    """
    Get the list of mailing list addresses on this MAIL server.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("environment variable MAIL_TOKEN is required")

    # 2. Attempt to get the list of mailing lists on the MAIL server
    response = httpx.get(
        url=f"{MAIL_SERVER}/lists",
        headers={
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
            "Authorization": f"Bearer {MAIL_TOKEN}",
        },
    )

    # 3. Parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"get lists request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = ListsGetResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. Print the list of mailing lists
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: ListsGetResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: ListsGetResponse) -> None:
    lists = response_obj.lists
    print("=== Mailing Lists ===")
    for list in lists:
        print(f"{list.get_address()} ({len(list.members)} members)")
