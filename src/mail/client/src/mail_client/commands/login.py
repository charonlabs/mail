# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.responses import PostAuthTokenResponse
from pydantic import ValidationError


def cmd_login(args: Namespace) -> None:
    """
    Log into a MAIL server with provided credentials.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_ADDRESS = os.getenv("MAIL_ADDRESS")
    if MAIL_ADDRESS is None:
        raise ValueError("environment variable MAIL_ADDRESS is required")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    if MAIL_PASSWORD is None:
        raise ValueError("environment variable MAIL_PASSWORD is required")

    # 2. Attempt to log into the MAIL server and obtain a JWT
    payload = {
        "grant_type": "password",
        "username": MAIL_ADDRESS,
        "password": MAIL_PASSWORD,
        "scope": "",
        "client_id": MAIL_ADDRESS,
        "client_secret": MAIL_PASSWORD,
    }
    response = httpx.post(
        url=f"{MAIL_SERVER}/auth/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Multi-Agent-Interface-Layer-CLI-Client/2.0.0 (github.com/charonlabs/mail)",
        },
        json=payload,
    )

    # 3. Parse and validate server response
    if response.status_code != 200:
        raise RuntimeError(
            f"login request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = PostAuthTokenResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 4. Print the JWT
    print(f"got access token: {response_obj.token}")
    print("set MAIL_TOKEN={token} in subsequent operations")
