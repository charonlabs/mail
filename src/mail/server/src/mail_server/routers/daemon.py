# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, Request
from mail_protocol.network.responses import (
    DaemonDeliverLocalResponse,
    DaemonDeliverRemoteResponse,
    DaemonMessageBufferClearResponse,
)

from mail_server.auth import validate_daemon
from mail_server.validators import validate_deliver_local_request

router = APIRouter(prefix="/daemon", tags=["daemon"])


@router.post(
    "/message-buffer/clear",
    summary="Obtain all messages in need of delivery",
    response_model=DaemonMessageBufferClearResponse,
)
async def clear_message_buffer(
    request: Request,
) -> DaemonMessageBufferClearResponse:
    backend = request.app.state.backend
    daemon = await validate_daemon(backend=backend, request=request)
    result = await backend.daemon_clear_message_buffer(daemon=daemon)
    return DaemonMessageBufferClearResponse(
        message_ids=result,
        metadata={},
    )


@router.post(
    "/deliver/local",
    summary="Upload new messages to deliver from local agent(s)",
    response_model=DaemonDeliverLocalResponse,
)
async def deliver_local_messages(request: Request) -> DaemonDeliverLocalResponse:
    backend = request.app.state.backend
    daemon = await validate_daemon(backend=backend, request=request)
    payload = await validate_deliver_local_request(request=request)
    result = await backend.daemon_deliver_local(daemon=daemon, payload=payload)
    return DaemonDeliverLocalResponse(
        messages=result,
        metadata={},
    )


@router.post(
    "/deliver/remote",
    summary="Upload new messages to deliver from remote agent(s)",
    response_model=DaemonDeliverRemoteResponse,
)
async def deliver_remote_messages(request: Request) -> DaemonDeliverRemoteResponse:
    raise NotImplementedError
