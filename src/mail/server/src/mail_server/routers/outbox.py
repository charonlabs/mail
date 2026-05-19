# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter

router = APIRouter(prefix="/outbox", tags=["outbox"])


@router.get("/")
async def get_outbox():
    return {"message": "Hello from GET /outbox!"}


@router.get("/{message_id}")
async def get_outbox_message(message_id: str):
    return {"message": f"Hello from GET /outbox/{message_id}!"}
