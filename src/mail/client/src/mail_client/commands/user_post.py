# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.requests import AdminUserPostRequest
from mail_protocol.network.responses import (
    AdminUserPostResponse,
)
from pydantic import ValidationError
from rich.console import Console


def cmd_user_post(args: Namespace) -> None:
    """
    Create a new user by local address on the MAIL server.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("environment variable MAIL_TOKEN is required")

    # 2. parse CLI input
    user_id = args.user_id

    # 3. get the password to use for the new user
    console = Console()
    user_password = console.input(prompt="user password:", password=True)

    # 4. Attempt to post the new user to the MAIL server
    payload = AdminUserPostRequest(user_id=user_id, user_password=user_password)
    response = httpx.post(
        url=f"{MAIL_SERVER}/admin/users",
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
            f"post user request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = AdminUserPostResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 5. Print the specified user
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: AdminUserPostResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: AdminUserPostResponse) -> None:
    user = response_obj.user
    print("=== User ===")
    print(f"User ID: {user.user_id}")
    print(f"Host: {user.host}")
