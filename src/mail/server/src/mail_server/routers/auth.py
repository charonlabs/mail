# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from mail_protocol.network.responses import (
    AuthLogoutPostResponse,
    AuthPasswordResetResponse,
    AuthRefreshPostResponse,
    AuthTokenPostResponse,
    AuthWhoamiGetResponse,
)

from mail_server.auth import (
    REFRESH_COOKIE_NAME,
    authenticate_user_agent,
    clear_refresh_cookie,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    is_interactive_principal,
    refresh_token_expiry,
    set_refresh_cookie,
    validate_user_agent,
)
from mail_server.validators import (
    validate_auth_password_reset_request,
    validate_auth_refresh_request,
)

ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("MAIL_JWT_EXPIRE_MINUTES")
if ACCESS_TOKEN_EXPIRE_MINUTES is None:
    raise RuntimeError("env var MAIL_JWT_EXPIRE_MINUTES must be set")
default_token_limit = int(ACCESS_TOKEN_EXPIRE_MINUTES)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/token",
    summary="Log in with an address and password to obtain an access token",
    response_model=AuthTokenPostResponse,
)
async def create_auth_token(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> AuthTokenPostResponse:
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

    # Interactive principals (users/admins) also get a refresh token, set as an
    # httpOnly cookie for browsers and returned in the body for the CLI. Agents
    # and daemons re-authenticate with their credentials and get none.
    refresh_token: str | None = None
    if is_interactive_principal(user_agent):
        refresh_token = generate_refresh_token()
        await backend.create_refresh_token(
            owner_address=user_agent.get_address(),
            token_hash=hash_refresh_token(refresh_token),
            family_id=f"fam_{uuid4()}",
            expires_at=refresh_token_expiry(),
        )
        set_refresh_cookie(response, refresh_token)

    return AuthTokenPostResponse(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_in=default_token_limit * 60,
        metadata={},
    )


async def _read_refresh_token(request: Request) -> str | None:
    """
    Extract the presented refresh token: the cookie (browsers) takes precedence,
    falling back to the request body (CLI / non-cookie clients).
    """

    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token is not None:
        return token
    payload = await validate_auth_refresh_request(request=request)
    return payload.refresh_token


@router.post(
    "/refresh",
    summary="Exchange a refresh token for a new access token (rotates the refresh token)",
    response_model=AuthRefreshPostResponse,
)
async def post_auth_refresh(
    request: Request,
    response: Response,
) -> AuthRefreshPostResponse:
    backend = request.app.state.backend
    credentials_exception = HTTPException(
        status_code=401,
        detail="could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = await _read_refresh_token(request)
    if token is None:
        raise credentials_exception

    record = await backend.get_refresh_token(hash_refresh_token(token))
    if record is None:
        raise credentials_exception

    # Absolute cap: a family expires at a fixed time, carried forward unchanged
    # across rotations.
    if record.expires_at <= datetime.now(UTC):
        raise credentials_exception

    # Reuse detection: a revoked or already-rotated token being presented means
    # the token was stolen (or replayed) — revoke the whole family.
    if record.revoked or record.rotated_at is not None:
        await backend.revoke_refresh_family(record.family_id)
        raise credentials_exception

    # Fail closed if the owner no longer exists (e.g. deleted by an admin).
    if not await backend.user_agent_exists(record.owner_address):
        await backend.revoke_refresh_family(record.family_id)
        raise credentials_exception

    new_refresh_token = generate_refresh_token()
    await backend.rotate_refresh_token(
        hash_refresh_token(token), hash_refresh_token(new_refresh_token)
    )

    access_token = create_access_token(
        data={"sub": record.owner_address},
        expires_delta=timedelta(minutes=default_token_limit),  # type: ignore
    )
    set_refresh_cookie(response, new_refresh_token)

    return AuthRefreshPostResponse(
        access_token=access_token,
        token_type="bearer",
        refresh_token=new_refresh_token,
        expires_in=default_token_limit * 60,
        metadata={},
    )


@router.post(
    "/logout",
    summary="Revoke the presented refresh token's family and clear the cookie",
    response_model=AuthLogoutPostResponse,
)
async def post_auth_logout(
    request: Request,
    response: Response,
) -> AuthLogoutPostResponse:
    backend = request.app.state.backend

    # Idempotent: revoke the family if the token resolves, but always succeed and
    # clear the cookie so a stale/absent token still logs the client out.
    token = await _read_refresh_token(request)
    if token is not None:
        record = await backend.get_refresh_token(hash_refresh_token(token))
        if record is not None:
            await backend.revoke_refresh_family(record.family_id)

    clear_refresh_cookie(response)
    return AuthLogoutPostResponse(status="success")


@router.get(
    "/whoami", summary="Get MAIL user-agent info", response_model=AuthWhoamiGetResponse
)
async def get_token_info(request: Request) -> AuthWhoamiGetResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    return AuthWhoamiGetResponse(
        user_agent=user_agent,
        metadata={},
    )


@router.post(
    "/password/reset",
    summary="Reset the user-agent's password",
    response_model=AuthPasswordResetResponse,
)
async def post_password_reset(request: Request) -> AuthPasswordResetResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    payload = await validate_auth_password_reset_request(request=request)
    try:
        result = await backend.reset_password(user_agent=user_agent, payload=payload)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if result != "success":
        raise HTTPException(status_code=400, detail="could not reset password")

    # A password change invalidates every existing session for this principal —
    # revoke all of their refresh-token families, forcing re-login everywhere.
    await backend.revoke_all_refresh_tokens(user_agent.get_address())

    return AuthPasswordResetResponse(
        status=result,
    )
