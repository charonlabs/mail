# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.requests import AdminWebhooksPostRequest
from mail_protocol.network.responses import (
    AdminWebhooksPostResponse,
)
from pydantic import ValidationError


def cmd_webhook_post(args: Namespace) -> None:
    """
    Create a new webhook on the MAIL server.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("environment variable MAIL_TOKEN is required")

    # 4. Attempt to post the new webhook to the MAIL server
    payload = AdminWebhooksPostRequest(
        url=args.url,
        events=args.events,
        secret=args.secret,
    )
    response = httpx.post(
        url=f"{MAIL_SERVER}/admin/webhooks",
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
            f"post webhook request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = AdminWebhooksPostResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 5. Print the specified swarm
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: AdminWebhooksPostResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: AdminWebhooksPostResponse) -> None:
    webhook = response_obj.webhook
    print("=== Webhook ===")
    print(f"ID: {webhook.webhook_id}")
    print(f"URL: {webhook.url}")
    print(f"Events: {webhook.events}")
    print(f"Secret: {webhook.secret}")
