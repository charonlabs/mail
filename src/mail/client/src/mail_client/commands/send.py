# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.requests import PostDraftSendRequest
from mail_protocol.network.responses import PostDraftSendResponse
from pydantic import ValidationError


def cmd_send(args: Namespace) -> None:
    """
    Send an existing message draft to the specified target address(es).
    """

    # 1. check that the required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("env var MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("env var MAIL_TOKEN is required")

    # 2. hit the server endpoint `POST /drafts/{draft_id}/send`
    payload = PostDraftSendRequest(
        recipients=args.to,
    )
    response = httpx.post(
        url=f"{MAIL_SERVER}/drafts/{args.draft_id}/send",
        headers={
            "Authorization": f"Bearer {MAIL_TOKEN}",
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
            "Content-Type": "application/json",
        },
        json=payload.model_dump(),
    )

    # 3. parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"send request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = PostDraftSendResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. print the new draft
    print(response_obj.model_dump_json())
