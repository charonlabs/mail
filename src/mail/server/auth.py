# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from os import getenv
from typing import Annotated

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from mail.protocol.core.instance import MAILInstanceType

load_dotenv()
JWT_SECRET = getenv("MAIL_SERVER_JWT_SECRET")
JWT_ALGORITHM = getenv("MAIL_SERVER_JWT_ALGORITHM")
jwt_lifetime_minutes = getenv("MAIL_SERVER_JWT_LIFETIME_MINUTES")
if not JWT_SECRET:
    raise ValueError("MAIL_SERVER_JWT_SECRET is not set")
if not JWT_ALGORITHM:
    raise ValueError("MAIL_SERVER_JWT_ALGORITHM is not set")
if not jwt_lifetime_minutes:
    raise ValueError("MAIL_SERVER_JWT_LIFETIME_MINUTES is not set")
JWT_LIFETIME_MINUTES = int(jwt_lifetime_minutes)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class TokenInfo(BaseModel):
    role: MAILInstanceType
    id: str


async def get_current_admin(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> TokenInfo:
    """
    Get the current client if they are an `admin`.
    """
    token_info = await get_current_client(token)
    if token_info.role != "admin":
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return token_info


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> TokenInfo:
    """
    Get the current client if they are a `user`.
    """
    token_info = await get_current_client(token)
    if token_info.role != "user":
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return token_info


async def get_current_swarm(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> TokenInfo:
    """
    Get the current client if they are a `swarm`.
    """
    token_info = await get_current_client(token)
    if token_info.role != "swarm":
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return token_info


async def get_current_admin_or_user(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> TokenInfo:
    """
    Get the current client if they are an `admin` or `user`.
    """
    token_info = await get_current_client(token)
    if token_info.role not in ["admin", "user"]:
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return token_info


async def get_current_client(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> TokenInfo:
    """
    Get the current client.
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="invalid token",
        headers={"WWW-Authenticate": "Bearer"}
    )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM]) # type: ignore
        id = payload.get("id")
        role = payload.get("role")
        if (not id) or (not role):
            raise credentials_exception
        return TokenInfo(id=id, role=role)
    except jwt.InvalidTokenError:
        raise credentials_exception