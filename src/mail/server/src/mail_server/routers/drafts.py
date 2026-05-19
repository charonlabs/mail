# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter
from mail_protocol.network.responses import (
    DeleteDraftResponse,
    GetDraftResponse,
    GetDraftsResponse,
    PostDraftResponse,
    PostDraftSendResponse,
)

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get(
    "/", summary="Get a list of message drafts", response_model=GetDraftsResponse
)
async def get_drafts() -> GetDraftsResponse:
    raise NotImplementedError


@router.post(
    "/", summary="Create a new message draft", response_model=PostDraftResponse
)
async def post_draft() -> PostDraftResponse:
    raise NotImplementedError


@router.get(
    "/{draft_id}",
    summary="Get a specific message draft by ID",
    response_model=GetDraftResponse,
)
async def get_draft(draft_id: str) -> GetDraftResponse:
    raise NotImplementedError


@router.delete(
    "/{draft_id}",
    summary="Delete a specific message draft by ID",
    response_model=DeleteDraftResponse,
)
async def delete_draft(draft_id: str) -> DeleteDraftResponse:
    raise NotImplementedError


@router.post(
    "/{draft_id}/send",
    summary="Send a message from an existing draft by ID",
    response_model=PostDraftSendResponse,
)
async def post_draft_send(draft_id: str) -> PostDraftSendResponse:
    raise NotImplementedError
