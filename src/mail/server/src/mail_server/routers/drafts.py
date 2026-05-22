# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import (
    DeleteDraftResponse,
    GetDraftResponse,
    GetDraftsResponse,
    PostDraftResponse,
    PostDraftSendResponse,
)

from mail_server.auth import validate_user_agent
from mail_server.validators import (
    validate_post_draft_request,
    validate_post_draft_send_request,
)

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get(
    "/", summary="Get a list of message drafts", response_model=GetDraftsResponse
)
async def get_drafts(request: Request) -> GetDraftsResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    try:
        result = await backend.get_drafts(user_agent=user_agent)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"draft box not found for address {user_agent}"
        )

    return GetDraftsResponse(entries=result, metadata={})


@router.post(
    "/", summary="Create a new message draft", response_model=PostDraftResponse
)
async def post_draft(request: Request) -> PostDraftResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    payload = await validate_post_draft_request(request)
    result = await backend.post_draft(user_agent=user_agent, payload=payload)

    return PostDraftResponse(
        entry=result,
        metadata={},
    )


@router.get(
    "/{draft_id}",
    summary="Get a specific message draft by ID",
    response_model=GetDraftResponse,
)
async def get_draft(request: Request) -> GetDraftResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    draft_id = request.path_params.get("draft_id")
    try:
        result = await backend.get_draft(user_agent=user_agent, draft_id=draft_id)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"draft with ID {draft_id} not found"
        )

    return GetDraftResponse(
        entry=result,
        metadata={},
    )


@router.delete(
    "/{draft_id}",
    summary="Delete a specific message draft by ID",
    response_model=DeleteDraftResponse,
)
async def delete_draft(request: Request) -> DeleteDraftResponse:
    raise NotImplementedError


@router.post(
    "/{draft_id}/send",
    summary="Send a message from an existing draft by ID",
    response_model=PostDraftSendResponse,
)
async def post_draft_send(request: Request) -> PostDraftSendResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    payload = await validate_post_draft_send_request(request)
    draft_id = request.path_params.get("draft_id")
    result = await backend.send_draft(
        user_agent=user_agent, draft_id=draft_id, payload=payload
    )
    return PostDraftSendResponse(
        message=result,
        metadata={},
    )
