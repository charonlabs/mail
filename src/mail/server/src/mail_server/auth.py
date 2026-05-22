# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from mail_protocol.core.user_agents import MAILDaemon, MAILUserAgent
from pwdlib import PasswordHash
from pydantic import BaseModel

from mail_server.backends.base import MAILServerBackend

SECRET_KEY = os.getenv("MAIL_JWT_SECRET_KEY")
if SECRET_KEY is None:
    raise RuntimeError("env var MAIL_JWT_SECRET_KEY must be set")
ALGORITHM = os.getenv("MAIL_JWT_ALGORITHM")
if ALGORITHM is None:
    raise RuntimeError("env var MAIL_JWT_ALGORITHM must be set")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    address: str | None = None


password_hash = PasswordHash.recommended()

DUMMY_HASH = password_hash.hash("dummypassword")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(plain_password: str) -> str:
    return password_hash.hash(plain_password)


async def get_user_agent(backend: MAILServerBackend, address: str):
    if await backend.user_agent_exists(address):
        user_agent = await backend.get_user_agent(address)
        return user_agent


async def authenticate_user_agent(
    backend: MAILServerBackend, address: str, password: str
):
    user_agent = await get_user_agent(backend=backend, address=address)
    if not user_agent:
        verify_password(password, DUMMY_HASH)
        return False
    if not verify_password(password, user_agent.hashed_password):
        return False
    return user_agent


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(payload=to_encode, key=SECRET_KEY, algorithm=ALGORITHM)  # type: ignore
    return encoded_jwt


async def validate_user_agent(
    backend: MAILServerBackend, request: Request
) -> MAILUserAgent:
    credentials_exception = HTTPException(
        status_code=401,
        detail="could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = request.headers.get("Authorization")
        if token is None:
            raise credentials_exception
        bearer_token = token.removeprefix("Bearer ")
        payload = jwt.decode(jwt=bearer_token, key=SECRET_KEY, algorithms=[ALGORITHM])  # type: ignore
        address = payload.get("sub")
        if address is None:
            raise credentials_exception
        token_data = TokenData(address=address)
    except InvalidTokenError:
        raise credentials_exception
    user_agent = await backend.get_user_agent(address)
    if user_agent is None:
        raise credentials_exception

    return user_agent


async def validate_daemon(backend: MAILServerBackend, request: Request) -> MAILDaemon:
    """
    Ensure that the request user-agent is a valid MAIL daemon.
    """

    user_agent = await validate_user_agent(backend=backend, request=request)

    if not isinstance(user_agent.user_agent, MAILDaemon):
        raise HTTPException(
            status_code=401,
            detail="could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_agent.user_agent
