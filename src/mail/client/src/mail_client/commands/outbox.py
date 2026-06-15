# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.responses import OutboxGetResponse
from pydantic import ValidationError

from mail_client.commands._box_filters import box_filter_params


def cmd_outbox(args: Namespace) -> None:
    """
    Get the current MAIL user's outbox.
    """

    # 1. check that the required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("env var MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("env var MAIL_TOKEN is required")

    # 2. hit the server endpoint `GET /outbox`
    response = httpx.get(
        url=f"{MAIL_SERVER}/outbox",
        headers={
            "Authorization": f"Bearer {MAIL_TOKEN}",
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
        },
        params=box_filter_params(args),
    )

    # 3. parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"get outbox request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = OutboxGetResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. print the user's outbox
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: OutboxGetResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: OutboxGetResponse) -> None:
    entries = response_obj.entries
    print("=== Outbox ===")
    for entry in entries:
        print(
            f"{entry.sent_at} | {entry.message_id} | {entry.subject} ({entry.body_size} characters)"
        )
