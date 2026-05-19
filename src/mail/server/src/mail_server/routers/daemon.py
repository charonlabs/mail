# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter

router = APIRouter(prefix="/daemon", tags=["daemon"])


@router.get("/queue")
async def get_message_queue():
    return {"message": "Hello from GET /daemon/queue!"}


@router.get("/queue/{message_id}")
async def get_message_in_queue(message_id: str):
    return {"message": f"Hello from GET /daemon/queue/{message_id}!"}


@router.delete("/queue/{message_id}")
async def delete_message_in_queue(message_id: str):
    return {"message": f"Hello from DELETE /daemon/queue/{message_id}!"}


@router.post("/deliver/local")
async def deliver_local_messages():
    return {"message": "Hello from POST /daemon/deliver/local!"}


@router.post("/deliver/remote")
async def deliver_remote_messages():
    return {"message": "Hello from POST /daemon/deliver/remote!"}
