# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.responses import (
    ListMemberPostResponse,
)
from pydantic import ValidationError


def cmd_list_subscribe(args: Namespace) -> None:
    """
    Subscribe to a mailing list on this MAIL server.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("environment variable MAIL_TOKEN is required")

    # 2. Attempt to subscribe to a specific mailing list on the MAIL server
    response = httpx.post(
        url=f"{MAIL_SERVER}/lists/{args.list_address}/subscribe",
        headers={
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
            "Authorization": f"Bearer {MAIL_TOKEN}",
        },
    )

    # 3. Parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"post list subscribe request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = ListMemberPostResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. Print the mailing list subscribe response
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: ListMemberPostResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: ListMemberPostResponse) -> None:
    mlist = response_obj.mail_list
    print("=== Mailing List ===")
    print(f"List ID: {mlist.list_id}")
    print(f"Address: {mlist.get_address()}")
    print(f"Owner: {mlist.owner}")
    print(f"Members: {mlist.members}")
    print(f"Visibility: {mlist.policy.visibility}")
    print(f"Join Policy: {mlist.policy.join_policy}")
    print(f"Send Policy: {mlist.policy.send_policy}")
    print(f"Created At: {mlist.created_at}")
    print(f"Updated At: {mlist.updated_at}")
