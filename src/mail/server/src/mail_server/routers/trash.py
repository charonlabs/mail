# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter
from mail_protocol.network.responses import (
    DeleteTrashMessageResponse,
    GetTrashMessageResponse,
    GetTrashResponse,
    PostTrashClearResponse,
)

router = APIRouter(prefix="/trash", tags=["trash"])


@router.get(
    "/", summary="Get a list of messages in trash", response_model=GetTrashResponse
)
async def get_trashed_messages() -> GetTrashResponse:
    raise NotImplementedError


@router.get(
    "/{message_id}",
    summary="Get a specific trashed message by ID",
    response_model=GetTrashMessageResponse,
)
async def get_trashed_message(message_id: str) -> GetTrashMessageResponse:
    raise NotImplementedError


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
