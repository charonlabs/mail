# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter
from mail_protocol.network.responses import GetOutboxMessageResponse, GetOutboxResponse

router = APIRouter(prefix="/outbox", tags=["outbox"])


@router.get(
    "/", summary="Get a list of outbox messages", response_model=GetOutboxResponse
)
async def get_outbox() -> GetOutboxResponse:
    raise NotImplementedError


@router.get(
    "/{message_id}",
    summary="Get a specific outbox message by ID",
    response_model=GetOutboxMessageResponse,
)
async def get_outbox_message(message_id: str) -> GetOutboxMessageResponse:
    raise NotImplementedError
