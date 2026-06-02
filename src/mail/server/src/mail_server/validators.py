# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import HTTPException, Request
from mail_protocol.network.requests import (
    AdminAgentPostRequest,
    AdminDaemonPostRequest,
    AdminSwarmPostRequest,
    AdminUserPostRequest,
    AuthPasswordResetRequest,
    DaemonDeliverLocalRequest,
    DraftPostRequest,
    DraftSendPostRequest,
)
from pydantic import ValidationError


#
# Draft endpoint validators
#
async def validate_post_draft_request(request: Request) -> DraftPostRequest:
    """
    Ensure the request payload is valid for `POST /drafts`.
    """

    try:
        body = await request.json()
        return DraftPostRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_post_draft_send_request(request: Request) -> DraftSendPostRequest:
    """
    Ensure the request payload is valid for `POST /drafts/{draft_id}/send`.
    """

    try:
        body = await request.json()
        return DraftSendPostRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


#
# Daemon endpoint validators
#
async def validate_deliver_local_request(
    request: Request,
) -> DaemonDeliverLocalRequest:
    """
    Ensure that the request payload is valid for `POST /daemon/deliver/local`.
    """

    try:
        body = await request.json()
        return DaemonDeliverLocalRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


#
# Admin endpoint validators
#
async def validate_admin_post_agent_request(
    request: Request,
) -> AdminAgentPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/agents`.
    """

    try:
        body = await request.json()
        return AdminAgentPostRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_post_daemon_request(
    request: Request,
) -> AdminDaemonPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/daemons`.
    """

    try:
        body = await request.json()
        return AdminDaemonPostRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_post_user_request(
    request: Request,
) -> AdminUserPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/users`.
    """

    try:
        body = await request.json()
        return AdminUserPostRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_post_swarm_request(
    request: Request,
) -> AdminSwarmPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/swarms`.
    """

    try:
        body = await request.json()
        return AdminSwarmPostRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


#
# Auth endpoint validators
#
async def validate_auth_password_reset_request(
    request: Request,
) -> AuthPasswordResetRequest:
    """
    Ensure that the request payload is valid for `POST /auth/password/reset`.
    """

    try:
        body = await request.json()
        return AuthPasswordResetRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )
