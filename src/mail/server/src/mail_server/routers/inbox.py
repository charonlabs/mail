# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import (
    DeleteInboxMessageResponse,
    GetInboxMessageResponse,
    GetInboxResponse,
)

from mail_server.auth import validate_user_agent

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get(
    "/",
    summary="Get a list of inbox messages",
    response_model=GetInboxResponse,
)
async def get_inbox(request: Request) -> GetInboxResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    try:
        result = await backend.get_inbox(user_agent)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"inbox for address {user_agent.get_address()} not found",
        )

    return GetInboxResponse(
        entries=result,
        metadata={},
    )


@router.get(
    "/{message_id}",
    summary="Get a specific inbox message by ID",
    response_model=GetInboxMessageResponse,
)
async def open_inbox_message(request: Request) -> GetInboxMessageResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    message_id = request.path_params.get("message_id")
    try:
        result = await backend.get_inbox_message(
            user_agent=user_agent, message_id=message_id
        )
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"message with ID {message_id} not found in inbox"
        )

    return GetInboxMessageResponse(
        entry=result,
        metadata={},
    )


@router.delete(
    "/{message_id}",
    summary="Move a specific inbox message by ID to trash",
    response_model=DeleteInboxMessageResponse,
)
async def delete_inbox_message(request: Request) -> DeleteInboxMessageResponse:
    raise NotImplementedError
