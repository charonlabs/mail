# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

import inspect
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from os import getenv
from typing import Annotated, Protocol

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from mail_protocol.core.instance import MAILInstanceType
from pydantic import BaseModel

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


class JWTSettings(BaseModel):
    secret: str
    algorithm: str = "HS256"
    lifetime_minutes: int = 60
    issuer: str | None = None


class TokenInfo(BaseModel):
    role: MAILInstanceType
    id: str


class APIKeyAuthBackend(Protocol):
    def authenticate_api_key(
        self,
        api_key: str,
    ) -> TokenInfo | None | Awaitable[TokenInfo | None]:
        """
        Resolve an API key to a MAIL client identity.
        """


class StaticAPIKeyAuthBackend:
    """
    Minimal in-memory backend for examples, tests, and local development.
    """

    def __init__(self, api_keys: dict[str, TokenInfo]) -> None:
        self._api_keys = dict(api_keys)

    def authenticate_api_key(self, api_key: str) -> TokenInfo | None:
        return self._api_keys.get(api_key)


@lru_cache
def get_auth_settings() -> JWTSettings:
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

    return JWTSettings(
        secret=secret,
        algorithm=algorithm,
        lifetime_minutes=int(lifetime_minutes_raw),
    )


class MAILServerAuth:
    """
    JWT issuer/verifier plus pluggable API-key lookup.
    """

    def __init__(
        self,
        settings: JWTSettings,
        api_key_backend: APIKeyAuthBackend | None = None,
    ) -> None:
        self.settings = settings
        self.api_key_backend = api_key_backend

    @classmethod
    def from_env(
        cls,
        api_key_backend: APIKeyAuthBackend | None = None,
    ) -> MAILServerAuth:
        return cls(settings=get_auth_settings(), api_key_backend=api_key_backend)

    async def authenticate_api_key(self, api_key: str) -> TokenInfo:
        if self.api_key_backend is None:
            raise HTTPException(
                status_code=501,
                detail="MAIL server login is not configured",
            )

        result = self.api_key_backend.authenticate_api_key(api_key)
        if inspect.isawaitable(result):
            result = await result

        if result is None:
            raise HTTPException(
                status_code=401,
                detail="invalid API key",
            )

        return result

    def create_access_token(self, token_info: TokenInfo) -> str:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.settings.lifetime_minutes)
        payload = {
            "sub": token_info.id,
            "id": token_info.id,
            "role": token_info.role,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        if self.settings.issuer:
            payload["iss"] = self.settings.issuer

        return jwt.encode(
            payload,
            self.settings.secret,
            algorithm=self.settings.algorithm,
        )

    def decode_access_token(self, token: str) -> TokenInfo:
        credentials_exception = HTTPException(
            status_code=401,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = jwt.decode(
                token,
                self.settings.secret,
                algorithms=[self.settings.algorithm],
                issuer=self.settings.issuer,
                options={"require": ["exp", "iat", "id", "role"]},
            )
            client_id = payload.get("id")
            role = payload.get("role")
            if (not client_id) or (not role):
                raise credentials_exception
            return TokenInfo(id=client_id, role=role)
        except jwt.InvalidTokenError as exc:
            raise credentials_exception from exc


def get_server_auth(request: Request) -> MAILServerAuth:
    auth = getattr(request.app.state, "mail_server_auth", None)
    if auth is None:
        raise HTTPException(
            status_code=501,
            detail="MAIL server auth is not configured",
        )
    return auth


async def get_current_admin(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    token_info = await get_current_client(request, token)
    if token_info.role != "admin":
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_info


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    token_info = await get_current_client(request, token)
    if token_info.role != "user":
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_info


async def get_current_swarm(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    token_info = await get_current_client(request, token)
    if token_info.role != "swarm":
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_info


async def get_current_admin_or_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    token_info = await get_current_client(request, token)
    if token_info.role not in ["admin", "user"]:
        raise HTTPException(
            status_code=401,
            detail="invalid role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_info


async def get_current_client(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenInfo:
    auth = get_server_auth(request)
    return auth.decode_access_token(token)
