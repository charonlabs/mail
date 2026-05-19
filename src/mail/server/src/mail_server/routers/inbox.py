# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter
from mail_protocol.network.responses import (
    DeleteInboxMessageResponse,
    GetInboxMessageResponse,
    GetInboxResponse,
)

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get(
    "/",
    summary="Get a list of inbox messages",
    response_model=GetInboxResponse,
)
async def get_inbox() -> GetInboxResponse:
    raise NotImplementedError


@router.get(
    "/{message_id}",
    summary="Get a specific inbox message by ID",
    response_model=GetInboxMessageResponse,
)
async def open_inbox_message(message_id: str) -> GetInboxMessageResponse:
    raise NotImplementedError


@router.delete(
    "/{message_id}",
    summary="Move a specific inbox message by ID to trash",
    response_model=DeleteInboxMessageResponse,
)
async def delete_inbox_message(message_id: str) -> DeleteInboxMessageResponse:
    raise NotImplementedError
