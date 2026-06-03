# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.requests import AdminDaemonPostRequest
from mail_protocol.network.responses import (
    AdminDaemonPostResponse,
)
from pydantic import ValidationError
from rich.console import Console


def cmd_daemon_post(args: Namespace) -> None:
    """
    Create a new daemon by local address on the MAIL server.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("environment variable MAIL_TOKEN is required")

    # 2. parse CLI input
    worker_name = args.worker_name

    # 3. get the password to use for the new daemon
    console = Console()
    daemon_password = console.input(prompt="daemon password:", password=True)

    # 4. Attempt to post the new daemon to the MAIL server
    payload = AdminDaemonPostRequest(
        worker_name=worker_name, daemon_password=daemon_password
    )
    response = httpx.post(
        url=f"{MAIL_SERVER}/admin/daemons",
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
            f"post daemon request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = AdminDaemonPostResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 5. Print the specified daemon
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: AdminDaemonPostResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: AdminDaemonPostResponse) -> None:
    daemon = response_obj.daemon
    print("=== Daemon ===")
    print(f"Worker Name: {daemon.worker_name}")
    print(f"Host: {daemon.host}")
