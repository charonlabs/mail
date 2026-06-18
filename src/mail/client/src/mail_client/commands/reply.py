# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.requests import DraftPostRequest, DraftSendPostRequest
from mail_protocol.network.responses import (
    DraftPostResponse,
    DraftSendPostResponse,
    InboxMessageGetResponse,
)
from pydantic import ValidationError

USER_AGENT = "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)"


def _reply_subject(original_subject: str) -> str:
    """
    Derive the default subject for a reply. An existing `Re:` prefix
    (case-insensitive) is preserved rather than duplicated.
    """

    if original_subject.lower().startswith("re:"):
        return original_subject
    return f"Re: {original_subject}"


def cmd_reply(args: Namespace) -> None:
    """
    Reply to an existing inbox message for the current MAIL user.

    Fetches the original message to derive the reply recipient (its sender)
    and a default `Re:` subject, creates a draft that references the original
    via `reply_to`, then sends it.
    """

    # 1. check that the required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("env var MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("env var MAIL_TOKEN is required")

    headers = {
        "Authorization": f"Bearer {MAIL_TOKEN}",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
    }

    # 2. fetch the original message from the user's inbox
    original_response = httpx.get(
        url=f"{MAIL_SERVER}/inbox/{args.message_id}",
        headers=headers,
    )
    if original_response.status_code != 200:
        raise RuntimeError(
            f"get inbox entry request to {MAIL_SERVER} failed with status code "
            f"{original_response.status_code}"
        )
    try:
        original_obj = InboxMessageGetResponse.model_validate(original_response.json())
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    original = original_obj.entry.message
    subject = args.subject if args.subject else _reply_subject(original.subject)

    # 3. create the reply draft, referencing the original via `reply_to`
    draft_payload = DraftPostRequest(
        subject=subject,
        body=args.body,
        reply_to=original.message_id,
        tags=args.tags,
    )
    draft_response = httpx.post(
        url=f"{MAIL_SERVER}/drafts",
        headers=headers,
        json=draft_payload.model_dump(),
    )
    if draft_response.status_code != 200:
        raise RuntimeError(
            f"post draft request to {MAIL_SERVER} failed with status code "
            f"{draft_response.status_code}"
        )
    try:
        draft_obj = DraftPostResponse.model_validate(draft_response.json())
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    draft_id = draft_obj.entry.draft.draft_id

    # 4. send the draft back to the original sender
    send_payload = DraftSendPostRequest(recipients=[original.sender])
    send_response = httpx.post(
        url=f"{MAIL_SERVER}/drafts/{draft_id}/send",
        headers=headers,
        json=send_payload.model_dump(),
    )
    if send_response.status_code != 200:
        raise RuntimeError(
            f"send request to {MAIL_SERVER} failed with status code "
            f"{send_response.status_code}"
        )
    try:
        send_obj = DraftSendPostResponse.model_validate(send_response.json())
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 5. print the sent reply
    match args.output:
        case "json":
            print(send_obj.model_dump_json())
        case "text":
            _print_text(send_obj)


def _print_text(response_obj: DraftSendPostResponse) -> None:
    message = response_obj.message
    print("=== Reply Sent ===")
    print(f"Message ID: {message.message_id}")
    print(f"In Reply To: {message.reply_to}")
    print(f"Sent At: {message.sent_at}")
    print(f"Sender: {message.sender}")
    print("Recipient(s):")
    for recipient in message.recipients:
        print(f"- {recipient}")
    print(f"Subject: {message.subject}")
    if message.tags:
        print(f"Tags: {', '.join(message.tags)}")
    print(f"Body:\n{message.body}\n")
