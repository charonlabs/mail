# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter
from mail_protocol.network.responses import (
    DeleteDaemonQueueMessageResponse,
    GetDaemonQueueMessageResponse,
    GetDaemonQueueResponse,
    PostDaemonDeliverLocalResponse,
    PostDaemonDeliverRemoteResponse,
)

router = APIRouter(prefix="/daemon", tags=["daemon"])


@router.get(
    "/queue",
    summary="Get a list of messages in the delivery queue",
    response_model=GetDaemonQueueResponse,
)
async def get_message_queue() -> GetDaemonQueueResponse:
    raise NotImplementedError


@router.get(
    "/queue/{message_id}",
    summary="Get a specific queued message by ID",
    response_model=GetDaemonQueueMessageResponse,
)
async def get_message_in_queue(message_id: str) -> GetDaemonQueueMessageResponse:
    raise NotImplementedError


@router.delete(
    "/queue/{message_id}",
    summary="Delete a specific queued message by ID",
    response_model=DeleteDaemonQueueMessageResponse,
)
async def delete_message_in_queue(message_id: str) -> DeleteDaemonQueueMessageResponse:
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
