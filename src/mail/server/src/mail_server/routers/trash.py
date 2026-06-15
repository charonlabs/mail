# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import (
    TrashClearPostResponse,
    TrashGetResponse,
    TrashMessageDeleteResponse,
    TrashMessageGetResponse,
)

from mail_server.auth import validate_user_agent
from mail_server.utils import build_box_metadata
from mail_server.validators import validate_box_filter_params

router = APIRouter(prefix="/trash", tags=["trash"])


@router.get(
    "/", summary="Get a list of messages in trash", response_model=TrashGetResponse
)
async def get_trashed_messages(request: Request) -> TrashGetResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    filters = await validate_box_filter_params(request)
    try:
        entries, total = await backend.get_trash(user_agent, filters)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"trash box not found for address {user_agent.get_address()}",
        )

    return TrashGetResponse(
        entries=entries,
        metadata=build_box_metadata(filters, total, len(entries)),
    )


@router.get(
    "/{message_id}",
    summary="Get a specific trashed message by ID",
    response_model=TrashMessageGetResponse,
)
async def get_trashed_message(request: Request) -> TrashMessageGetResponse:
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

    return TrashMessageGetResponse(
        entry=result,
        metadata={},
    )


@router.delete(
    "/{message_id}",
    summary="Delete a specific trashed message by ID",
    response_model=TrashMessageDeleteResponse,
)
async def delete_trashed_message(message_id: str) -> TrashMessageDeleteResponse:
    raise NotImplementedError


@router.post(
    "/clear",
    summary="Remove all exisisting messages from trash",
    response_model=TrashClearPostResponse,
)
async def post_trash_clear() -> TrashClearPostResponse:
    raise NotImplementedError
