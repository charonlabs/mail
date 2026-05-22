# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.responses import GetTrashMessageResponse
from pydantic import ValidationError


def cmd_trash_open(args: Namespace) -> None:
    """
    Open a specific message by ID in the user-agent's trash box.
    """

    # 1. check that the required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("env var MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("env var MAIL_TOKEN is required")

    # 2. hit the server endpoint `GET /trash/{message_id}`
    response = httpx.get(
        url=f"{MAIL_SERVER}/trash/{args.message_id}",
        headers={
            "Authorization": f"Bearer {MAIL_TOKEN}",
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
        },
    )

    # 3. parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"get trash entry request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = GetTrashMessageResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. print the returned trash entry
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: GetTrashMessageResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: GetTrashMessageResponse) -> None:
    entry = response_obj.entry
    message = entry.message
    print("=== Message ===")
    print(f"Message ID: {message.message_id}")
    print(f"Sent At: {message.sent_at}")
    print(f"Sender: {message.sender}")
    print("Recipient(s):")
    for recipient in message.recipients:
        print(f"- {recipient}")
    print(f"Subject: {message.subject}")
    print(f"Body:\n{message.body}\n")
    print("=== Trash Entry Data ===")
    print(f"Trashed At: {entry.trashed_at}")
