# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/")
async def get_inbox():
    return {"message": "Hello from GET /inbox!"}


@router.get("/{message_id}")
async def open_inbox_message(message_id: str):
    return {"message": f"Hello from GET /inbox/{message_id}!"}
