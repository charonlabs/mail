# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import HTTPException, Request
from mail_protocol.network.requests import (
    PostDaemonDeliverLocalRequest,
    PostDraftRequest,
    PostDraftSendRequest,
)
from pydantic import ValidationError


async def validate_post_draft_request(request: Request) -> PostDraftRequest:
    """
    Ensure the request payload is valid for `POST /drafts`.
    """

    try:
        body = await request.json()
        return PostDraftRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_post_draft_send_request(request: Request) -> PostDraftSendRequest:
    """
    Ensure the request payload is valid for `POST /drafts/{draft_id}/send`.
    """

    try:
        body = await request.json()
        return PostDraftSendRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_deliver_local_request(
    request: Request,
) -> PostDaemonDeliverLocalRequest:
    """
    Ensure that the request payload is valid for `POST /daemon/deliver/local`.
    """

    try:
        body = await request.json()
        return PostDaemonDeliverLocalRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )
