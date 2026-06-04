# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.responses import (
    AdminWebhooksDeleteResponse,
)
from pydantic import ValidationError


def cmd_webhook_delete(args: Namespace) -> None:
    """
    Delete a specific webhook by ID on the MAIL server.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("environment variable MAIL_TOKEN is required")

    # 2. Attempt to delete the specific webhook by ID on the MAIL server
    response = httpx.delete(
        url=f"{MAIL_SERVER}/admin/webhooks/{args.webhook_id}",
        headers={
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
            "Authorization": f"Bearer {MAIL_TOKEN}",
        },
    )

    # 3. Parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"delete webhook request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = AdminWebhooksDeleteResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. Print the specified webhook
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: AdminWebhooksDeleteResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: AdminWebhooksDeleteResponse) -> None:
    webhook = response_obj.webhook
    print("=== Webhook ===")
    print(f"ID: {webhook.webhook_id}")
    print(f"URL: {webhook.url}")
    print(f"Events: {webhook.events}")
    print(f"Secret: {webhook.secret}")
