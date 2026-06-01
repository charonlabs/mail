# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from argparse import Namespace

import httpx
from mail_protocol.network.requests import PostAdminAgentRequest
from mail_protocol.network.responses import (
    PostAdminAgentResponse,
)
from pydantic import ValidationError
from rich.console import Console


def cmd_agent_post(args: Namespace) -> None:
    """
    Create a new agent by local address on the MAIL server.
    """

    # 1. check that required env vars are provided
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        raise ValueError("environment variable MAIL_SERVER is required")
    MAIL_TOKEN = os.getenv("MAIL_TOKEN")
    if MAIL_TOKEN is None:
        raise ValueError("environment variable MAIL_TOKEN is required")

    # 2. parse CLI input
    split_at = args.local_address.split("@")
    if len(split_at) != 2:
        raise ValueError(f"invalid local agent address: {args.local_address}")
    agent, swarm = split_at

    # 3. get the password to use for the new agent
    console = Console()
    agent_password = console.input(prompt="agent password:", password=True)

    # 4. Attempt to post the new agent to the MAIL server
    payload = PostAdminAgentRequest(
        agent_name=agent, swarm_name=swarm, agent_password=agent_password
    )
    response = httpx.post(
        url=f"{MAIL_SERVER}/admin/agents",
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
            f"post agent request to {MAIL_SERVER} failed with status code {response.status_code}"
        )

    response_json = response.json()
    try:
        response_obj = PostAdminAgentResponse.model_validate(response_json)
    except ValidationError as e:
        raise RuntimeError(f"response validation failed: {e}")

    # 5. Print the specified agent
    match args.output:
        case "json":
            _print_json(response_obj)
        case "text":
            _print_text(response_obj)


def _print_json(response_obj: PostAdminAgentResponse) -> None:
    print(response_obj.model_dump_json())


def _print_text(response_obj: PostAdminAgentResponse) -> None:
    agent = response_obj.agent
    print("=== Agent ===")
    print(f"Name: {agent.name}")
    print(f"Swarm: {agent.swarm}")
    print(f"Host: {agent.host}")
