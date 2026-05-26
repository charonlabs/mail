# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.requests import PostDraftRequest
from mail_protocol.network.responses import PostDraftResponse
from pydantic import ValidationError


def cmd_compose(args: Namespace) -> None:
    """
    Create a new message draft for the current MAIL user.
    """

    # 1. check that the required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("env var MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("env var MAIL_TOKEN is required")

    # 2. hit the server endpoint `POST /drafts`
    payload = PostDraftRequest(
        subject=args.subject,
        body=args.body,
    )
    response = httpx.post(
        url=f"{MAIL_SERVER}/drafts/",
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
            f"post draft request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = PostDraftResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. print the new draft
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: PostDraftResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: PostDraftResponse) -> None:
    entry = response_obj.entry
    draft = entry.draft

    print("=== Draft ===")
    print(f"Draft ID: {draft.draft_id}")
    print(f"Created At: {draft.created_at}")
    print(f"Subject: {draft.subject}")
    print(f"Body:\n{draft.body}\n")
    print("=== Entry Data ===")
    print(f"Sent At: {entry.sent_at}")
    print(f"Sent By: {entry.sent_by}")
