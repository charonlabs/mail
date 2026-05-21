# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import os
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security.oauth2 import OAuth2PasswordRequestForm

from mail_server.auth import Token, authenticate_user_agent, create_access_token

ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("MAIL_JWT_EXPIRE_MINUTES")
if ACCESS_TOKEN_EXPIRE_MINUTES is None:
    raise RuntimeError("env var MAIL_JWT_EXPIRE_MINUTES must be set")

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/token")
async def create_auth_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
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
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)  # type: ignore
    access_token = create_access_token(
        data={"sub": user_agent.get_address()}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/whoami")
async def get_token_info():
    return {"message": "Hello from GET /auth/whoami!"}
