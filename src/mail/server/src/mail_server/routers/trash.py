# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter

router = APIRouter(prefix="/trash", tags=["trash"])


@router.get("/")
async def get_trashed_messages():
    return {"message": "Hello from GET /trash!"}


@router.get("/{message_id}")
async def get_trashed_message(message_id: str):
    return {"message": f"Hello from GET /trash/{message_id}!"}
