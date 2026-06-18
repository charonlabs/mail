# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.core.messages import MAILMessage
from mail_protocol.network.requests import DraftPostRequest, DraftSendPostRequest
from mail_protocol.network.responses import (
    DraftPostResponse,
    DraftSendPostResponse,
    InboxMessageGetResponse,
)
from pydantic import ValidationError

USER_AGENT = "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)"


def _forward_subject(original_subject: str) -> str:
    """
    Derive the default subject for a forward. An existing `Fwd:` prefix
    (case-insensitive) is preserved rather than duplicated.
    """

    if original_subject.lower().startswith("fwd:"):
        return original_subject
    return f"Fwd: {original_subject}"


def _forward_body(original: MAILMessage, note: str | None) -> str:
    """
    Encode the original message into the forwarded body, optionally prefixed
    with the forwarding user-agent's own note. The quoted block mirrors the
    familiar email "forwarded message" convention so the original sender,
    recipients, subject, and body remain legible to the new recipient(s).
    """

    forwarded_block = (
        "---------- Forwarded message ----------\n"
        f"From: {original.sender}\n"
        f"Date: {original.sent_at}\n"
        f"Subject: {original.subject}\n"
        f"To: {', '.join(original.recipients)}\n"
        "\n"
        f"{original.body}"
    )
    if note:
        return f"{note}\n\n{forwarded_block}"
    return forwarded_block


def cmd_forward(args: Namespace) -> None:
    """
    Forward an existing inbox message to one or more new recipient(s).

    Fetches the original message, builds a draft whose body encodes the
    original (sender, recipients, subject, and body) along with an optional
    note, defaults the subject to `Fwd: <original subject>`, then sends it to
    the specified recipient(s).
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
    subject = args.subject if args.subject else _forward_subject(original.subject)

    # 3. create the forward draft, encoding the original message in the body
    draft_payload = DraftPostRequest(
        subject=subject,
        body=_forward_body(original, args.note),
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

    # 4. send the draft to the specified recipient(s)
    send_payload = DraftSendPostRequest(recipients=args.to)
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

    # 5. print the forwarded message
    match args.output:
        case "json":
            print(send_obj.model_dump_json())
        case "text":
            _print_text(send_obj)


def _print_text(response_obj: DraftSendPostResponse) -> None:
    message = response_obj.message
    print("=== Message Forwarded ===")
    print(f"Message ID: {message.message_id}")
    print(f"Sent At: {message.sent_at}")
    print(f"Sender: {message.sender}")
    print("Recipient(s):")
    for recipient in message.recipients:
        print(f"- {recipient}")
    print(f"Subject: {message.subject}")
    if message.tags:
        print(f"Tags: {', '.join(message.tags)}")
    print(f"Body:\n{message.body}\n")
