# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("/")
async def get_drafts():
    return {"message": "Hello from GET /drafts!"}


@router.get("/{draft_id}")
async def get_draft(draft_id: str):
    return {"message": f"Hello from GET /drafts/{draft_id}!"}


@router.delete("/{draft_id}")
async def delete_draft(draft_id: str):
    return {"message": f"Hello from DELETE /drafts/{draft_id}!"}
