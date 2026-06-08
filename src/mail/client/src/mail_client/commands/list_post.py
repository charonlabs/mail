# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.requests import AdminListPostRequest
from mail_protocol.network.responses import (
    AdminListPostResponse,
)
from pydantic import ValidationError


def cmd_list_post(args: Namespace) -> None:
    """
    Create a new mailing list on the MAIL server.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("environment variable MAIL_TOKEN is required")

    # 4. Attempt to post the new list to the MAIL server
    payload = AdminListPostRequest(
        name=args.name,
        swarm_name=args.swarm_name,
        owner=args.owner,
        members=args.members,
    )
    response = httpx.post(
        url=f"{MAIL_SERVER}/admin/lists",
        headers={
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
            "Authorization": f"Bearer {MAIL_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload.model_dump(),
    )

    # 4. Parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"post list request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = AdminListPostResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 5. Print the specified mailing list
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: AdminListPostResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: AdminListPostResponse) -> None:
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
