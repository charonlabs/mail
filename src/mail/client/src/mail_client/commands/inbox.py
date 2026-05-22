# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.responses import GetInboxResponse
from pydantic import ValidationError


def cmd_inbox(args: Namespace) -> None:
    """
    Open the current MAIL user's inbox.
    """

    # 1. check that the required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("env var MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("env var MAIL_TOKEN is required")

    # 2. hit the server endpoint `GET /inbox`
    response = httpx.get(
        url=f"{MAIL_SERVER}/inbox/",
        headers={
            "Authorization": f"Bearer {MAIL_TOKEN}",
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
        },
    )

    # 3. parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"get inbox request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = GetInboxResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. print the user's inbox
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: GetInboxResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: GetInboxResponse) -> None:
    entries = response_obj.entries
    print("=== Outbox ===")
    for entry in entries:
        print(
            f"{entry.received_at} | {entry.message_id} | [{entry.sender}] {entry.subject} ({entry.body_size} characters)"
        )
