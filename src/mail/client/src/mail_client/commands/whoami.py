# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.responses import GetAuthWhoamiResponse
from pydantic import ValidationError


def cmd_whoami(args: Namespace) -> None:
    """
    Get info on this MAIL server user-agent.
    """

    # 1. check that the required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("env var MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("env var MAIL_TOKEN is required")

    # 2. hit the server endpoint `GET /auth/whoami`
    response = httpx.get(
        url=f"{MAIL_SERVER}/auth/whoami",
        headers={
            "Authorization": f"Bearer {MAIL_TOKEN}",
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
        },
    )

    # 3. parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"get whoami request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = GetAuthWhoamiResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. print the user-agent information
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: GetAuthWhoamiResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: GetAuthWhoamiResponse) -> None:
    user_agent = response_obj.user_agent
    print("=== User-Agent ===")
    print(f"Type: {user_agent.user_agent.ua_type}")
    print(f"Address: {user_agent.get_address()}")
