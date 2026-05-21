# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import GetOutboxMessageResponse, GetOutboxResponse

from mail_server.auth import validate_user_agent

router = APIRouter(prefix="/outbox", tags=["outbox"])


@router.get(
    "/", summary="Get a list of outbox messages", response_model=GetOutboxResponse
)
async def get_outbox(request: Request) -> GetOutboxResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    try:
        result = await backend.get_outbox(user_agent=user_agent)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"outbox for address {user_agent.get_address()} not found",
        )

    return GetOutboxResponse(
        outbox=result,
        metadata={},
    )


@router.get(
    "/{message_id}",
    summary="Get a specific outbox message by ID",
    response_model=GetOutboxMessageResponse,
)
async def get_outbox_message(request: Request) -> GetOutboxMessageResponse:
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

    return GetOutboxMessageResponse(
        message=result,
        metadata={},
    )
