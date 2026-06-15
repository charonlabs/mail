# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import (
    InboxGetResponse,
    InboxMessageDeleteResponse,
    InboxMessageGetResponse,
)

from mail_server.auth import validate_user_agent
from mail_server.utils import build_box_metadata
from mail_server.validators import validate_box_filter_params

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get(
    "",
    summary="Get a list of inbox messages",
    response_model=InboxGetResponse,
)
async def get_inbox(request: Request) -> InboxGetResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    filters = await validate_box_filter_params(request)
    try:
        entries, total = await backend.get_inbox(user_agent, filters)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"inbox for address {user_agent.get_address()} not found",
        )

    return InboxGetResponse(
        entries=entries,
        metadata=build_box_metadata(filters, total, len(entries)),
    )


@router.get(
    "/{message_id}",
    summary="Get a specific inbox message by ID",
    response_model=InboxMessageGetResponse,
)
async def open_inbox_message(request: Request) -> InboxMessageGetResponse:
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

    return InboxMessageGetResponse(
        entry=result,
        metadata={},
    )


@router.delete(
    "/{message_id}",
    summary="Move a specific inbox message by ID to trash",
    response_model=InboxMessageDeleteResponse,
)
async def delete_inbox_message(request: Request) -> InboxMessageDeleteResponse:
    raise NotImplementedError
