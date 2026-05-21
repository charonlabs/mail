# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import (
    DeleteTrashMessageResponse,
    GetTrashMessageResponse,
    GetTrashResponse,
    PostTrashClearResponse,
)

from mail.server.src.mail_server.auth import validate_user_agent

router = APIRouter(prefix="/trash", tags=["trash"])


@router.get(
    "/", summary="Get a list of messages in trash", response_model=GetTrashResponse
)
async def get_trashed_messages(request: Request) -> GetTrashResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    try:
        result = await backend.get_trash(user_agent=user_agent)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"trash box not found for address {user_agent.get_address()}",
        )

    return GetTrashResponse(
        trash=result,
        metadata={},
    )


@router.get(
    "/{message_id}",
    summary="Get a specific trashed message by ID",
    response_model=GetTrashMessageResponse,
)
async def get_trashed_message(request: Request) -> GetTrashMessageResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    message_id = request.path_params.get("message_id")
    try:
        result = await backend.get_trash_message(
            user_agent=user_agent, message_id=message_id
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"no message with ID {message_id} found in trash box",
        )

    return GetTrashMessageResponse(
        message=result,
        metadata={},
    )


@router.delete(
    "/{message_id}",
    summary="Delete a specific trashed message by ID",
    response_model=DeleteTrashMessageResponse,
)
async def delete_trashed_message(message_id: str) -> DeleteTrashMessageResponse:
    raise NotImplementedError


@router.post(
    "/clear",
    summary="Remove all exisisting messages from trash",
    response_model=PostTrashClearResponse,
)
async def post_trash_clear() -> PostTrashClearResponse:
    raise NotImplementedError
