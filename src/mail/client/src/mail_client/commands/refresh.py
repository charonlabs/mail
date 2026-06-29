# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.responses import AuthRefreshPostResponse
from pydantic import ValidationError


def cmd_refresh(args: Namespace) -> None:
    """
    Exchange a refresh token for a renewed access token.

    The refresh token is rotated server-side: the value in ``MAIL_REFRESH_TOKEN``
    is invalidated and a replacement is returned, which the caller should store
    for the next refresh.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_REFRESH_TOKEN = os.getenv("MAIL_REFRESH_TOKEN")
    if MAIL_REFRESH_TOKEN is None:
        raise ValueError("environment variable MAIL_REFRESH_TOKEN is required")

    # 2. hit the server endpoint `POST /auth/refresh`. The CLI can't use the
    # httpOnly cookie browsers rely on, so the token is sent in the body.
    response = httpx.post(
        url=f"{MAIL_SERVER}/auth/refresh",
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
        },
        json={"refresh_token": MAIL_REFRESH_TOKEN},
    )

    # 3. parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"refresh request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = AuthRefreshPostResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. print the renewed token(s)
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: AuthRefreshPostResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: AuthRefreshPostResponse) -> None:
    print("Got token:")
    print(response_obj.access_token)
    print()
    print("Run subsequent commands with `MAIL_TOKEN={token}`")
    if response_obj.refresh_token is not None:
        print()
        print("Got rotated refresh token:")
        print(response_obj.refresh_token)
        print()
        print(
            "Your previous refresh token is now invalid. "
            "Update `MAIL_REFRESH_TOKEN` with this value."
        )
