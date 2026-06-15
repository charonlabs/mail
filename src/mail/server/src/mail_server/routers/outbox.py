# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import OutboxGetResponse, OutboxMessageGetResponse

from mail_server.auth import validate_user_agent
from mail_server.utils import build_box_metadata
from mail_server.validators import validate_box_filter_params

router = APIRouter(prefix="/outbox", tags=["outbox"])


@router.get(
    "/", summary="Get a list of outbox messages", response_model=OutboxGetResponse
)
async def get_outbox(request: Request) -> OutboxGetResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    filters = await validate_box_filter_params(request)
    try:
        entries, total = await backend.get_outbox(user_agent, filters)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"outbox for address {user_agent.get_address()} not found",
        )

    return OutboxGetResponse(
        entries=entries,
        metadata=build_box_metadata(filters, total, len(entries)),
    )


@router.get(
    "/{message_id}",
    summary="Get a specific outbox message by ID",
    response_model=OutboxMessageGetResponse,
)
async def get_outbox_message(request: Request) -> OutboxMessageGetResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    message_id = request.path_params.get("message_id")
    try:
        result = await backend.get_outbox_message(
            user_agent=user_agent, message_id=message_id
        )
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"message with ID {message_id} not found in outbox"
        )

    return OutboxMessageGetResponse(
        entry=result,
        metadata={},
    )
