# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from fastapi import HTTPException, Request
from pydantic import ValidationError

from mail.server.types import (
    PostInterswarmMessageRequest,
    PostMessageRequest,
)


async def validate_post_message_request(request: Request) -> PostMessageRequest:
    """
    Validate a request body to the endpoint `POST /message`.
    """
    try:
        body_json = await request.json()
        return PostMessageRequest.model_validate(body_json)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"invalid request body: {e}"
        )


async def validate_post_interswarm_message_request(request: Request) -> PostInterswarmMessageRequest:
    """
    Validate a request body to the endpoint `POST /interswarm/message`.
    """
    try:
        body_json = await request.json()
        return PostInterswarmMessageRequest.model_validate(body_json)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"invalid request body: {e}"
        )


def ensure_swarm_names_match(
    client_id: str,
    source_swarm_name: str,
) -> None:
    """
    Ensure that the source swarm name matches the client ID.
    """
    if source_swarm_name != client_id:
        raise HTTPException(
            status_code=400,
            detail="source swarm name does not match client ID"
        )