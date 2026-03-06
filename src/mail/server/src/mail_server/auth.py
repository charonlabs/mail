# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

from functools import lru_cache
from os import getenv
from typing import Annotated

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from mail_protocol.core.instance import MAILInstanceType
from pydantic import BaseModel

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


class AuthSettings(BaseModel):
    secret: str
    algorithm: str
    lifetime_minutes: int


class TokenInfo(BaseModel):
    role: MAILInstanceType
    id: str


@lru_cache
def get_auth_settings() -> AuthSettings:
    load_dotenv()

    secret = getenv("MAIL_SERVER_JWT_SECRET")
    algorithm = getenv("MAIL_SERVER_JWT_ALGORITHM")
    lifetime_minutes_raw = getenv("MAIL_SERVER_JWT_LIFETIME_MINUTES")

    missing = [
        env_var
        for env_var, value in [
            ("MAIL_SERVER_JWT_SECRET", secret),
            ("MAIL_SERVER_JWT_ALGORITHM", algorithm),
            ("MAIL_SERVER_JWT_LIFETIME_MINUTES", lifetime_minutes_raw),
        ]
        if not value
    ]
    if missing:
        missing_joined = ", ".join(missing)
        raise RuntimeError(f"missing MAIL server auth environment variables: {missing_joined}")

    return AuthSettings(
        secret=secret,
        algorithm=algorithm,
        lifetime_minutes=int(lifetime_minutes_raw),
    )


async def get_current_admin(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    """
    Get the current client if they are an `admin`.
    """
    token_info = await get_current_client(token)
    if token_info.role != "admin":
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_info


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    """
    Get the current client if they are a `user`.
    """
    token_info = await get_current_client(token)
    if token_info.role != "user":
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_info


async def get_current_swarm(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    """
    Get the current client if they are a `swarm`.
    """
    token_info = await get_current_client(token)
    if token_info.role != "swarm":
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_info


async def get_current_admin_or_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    """
    Get the current client if they are an `admin` or `user`.
    """
    token_info = await get_current_client(token)
    if token_info.role not in ["admin", "user"]:
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_info


async def get_current_client(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    """
    Get the current client.
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        settings = get_auth_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        payload = jwt.decode(token, settings.secret, algorithms=[settings.algorithm])  # type: ignore[arg-type]
        client_id = payload.get("id")
        role = payload.get("role")
        if (not client_id) or (not role):
            raise credentials_exception
        return TokenInfo(id=client_id, role=role)
    except jwt.InvalidTokenError as exc:
        raise credentials_exception from exc
