# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from mail_protocol.network.federation import MAILFederationErrorResponse
from mail_protocol.network.requests import DaemonDeliverLocalRequest
from mail_protocol.network.responses import (
    DaemonDeliverLocalResponse,
    DaemonMessageBufferClearResponse,
)

from mail_server.auth import validate_daemon

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
    daemon = await validate_daemon(
        backend=backend, request=request, required_scope="deliver:local"
    )
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
async def deliver_local_messages(
    request: Request, payload: DaemonDeliverLocalRequest
) -> DaemonDeliverLocalResponse:
    backend = request.app.state.backend
    daemon = await validate_daemon(
        backend=backend, request=request, required_scope="deliver:local"
    )
    result = await backend.daemon_deliver_local(daemon=daemon, payload=payload)
    return DaemonDeliverLocalResponse(
        messages=result,
        metadata={},
    )


@router.post(
    "/deliver/remote",
    status_code=410,
    response_model=MAILFederationErrorResponse,
    summary="Reject the removed unsigned remote-delivery endpoint",
)
async def deliver_remote_messages(request: Request) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=410,
        content={
            "code": "federation_v1_required",
            "detail": (
                "unsigned remote delivery has been removed; use signed Federation v1"
            ),
        },
    )
