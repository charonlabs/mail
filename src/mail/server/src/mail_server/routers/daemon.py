# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter
from mail_protocol.network.responses import (
    PostDaemonDeliverLocalResponse,
    PostDaemonDeliverRemoteResponse,
    PostDaemonMessageBufferClearResponse,
)

router = APIRouter(prefix="/daemon", tags=["daemon"])


@router.post(
    "/message-buffer/clear",
    summary="Obtain all messages in need of delivery",
    response_model=PostDaemonMessageBufferClearResponse,
)
async def clear_message_buffer() -> PostDaemonMessageBufferClearResponse:
    raise NotImplementedError


@router.post(
    "/deliver/local",
    summary="Upload new messages to deliver from local agent(s)",
    response_model=PostDaemonDeliverLocalResponse,
)
async def deliver_local_messages() -> PostDaemonDeliverLocalResponse:
    raise NotImplementedError


@router.post(
    "/deliver/remote",
    summary="Upload new messages to deliver from remote agent(s)",
    response_model=PostDaemonDeliverRemoteResponse,
)
async def deliver_remote_messages() -> PostDaemonDeliverRemoteResponse:
    raise NotImplementedError
