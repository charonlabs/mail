# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from mail_protocol.network.responses import (
    GetAuthWhoamiResponse,
    PostAuthPasswordResetResponse,
    PostAuthTokenResponse,
)

from mail_server.auth import (
    authenticate_user_agent,
    create_access_token,
    validate_user_agent,
)

ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("MAIL_JWT_EXPIRE_MINUTES")
if ACCESS_TOKEN_EXPIRE_MINUTES is None:
    raise RuntimeError("env var MAIL_JWT_EXPIRE_MINUTES must be set")
default_token_limit = int(ACCESS_TOKEN_EXPIRE_MINUTES)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/token",
    summary="Log in with an address and password to obtain an access token",
    response_model=PostAuthTokenResponse,
)
async def create_auth_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> PostAuthTokenResponse:
    backend = request.app.state.backend
    user_agent = await authenticate_user_agent(
        backend=backend, address=form_data.username, password=form_data.password
    )
    if not user_agent:
        raise HTTPException(
            status_code=401,
            detail="incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=default_token_limit)  # type: ignore
    access_token = create_access_token(
        data={"sub": user_agent.get_address()}, expires_delta=access_token_expires
    )
    return PostAuthTokenResponse(
        access_token=access_token,
        token_type="bearer",
        metadata={},
    )


@router.get(
    "/whoami", summary="Get MAIL user-agent info", response_model=GetAuthWhoamiResponse
)
async def get_token_info(request: Request) -> GetAuthWhoamiResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    return GetAuthWhoamiResponse(
        user_agent=user_agent,
        metadata={},
    )


@router.post(
    "/password/reset",
    summary="Reset the user-agent's password",
    response_model=PostAuthPasswordResetResponse,
)
async def post_password_reset(request: Request) -> PostAuthPasswordResetResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    payload = await validate_auth_password_reset_request(request=request)
