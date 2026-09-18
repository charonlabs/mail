# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import hashlib
import os
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, Request, Response
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from mail_protocol.core.federation import mail_address_host
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
)
from mail_protocol.core.validators import validate_daemon_scopes
from pwdlib import PasswordHash
from pydantic import BaseModel

from mail_server.backends.base import MAILServerBackend

SECRET_KEY = os.getenv("MAIL_JWT_SECRET_KEY")
if SECRET_KEY is None:
    raise RuntimeError("env var MAIL_JWT_SECRET_KEY must be set")
ALGORITHM = os.getenv("MAIL_JWT_ALGORITHM")
if ALGORITHM is None:
    raise RuntimeError("env var MAIL_JWT_ALGORITHM must be set")

_REFRESH_TOKEN_EXPIRE_DAYS = os.getenv("MAIL_REFRESH_TOKEN_EXPIRE_DAYS")
if _REFRESH_TOKEN_EXPIRE_DAYS is None:
    raise RuntimeError("env var MAIL_REFRESH_TOKEN_EXPIRE_DAYS must be set")
REFRESH_TOKEN_EXPIRE_DAYS = int(_REFRESH_TOKEN_EXPIRE_DAYS)

# Refresh-token cookie configuration.
#
# The cookie is scoped to ``/auth`` so it is sent to ``/auth/refresh`` and
# ``/auth/logout`` (and only those auth endpoints) — never to the wider API,
# which authenticates exclusively via the ``Authorization`` header and so stays
# CSRF-immune. ``Secure`` defaults on; set ``MAIL_COOKIE_SECURE=false`` for
# local ``http://`` development.
REFRESH_COOKIE_NAME = "mail_refresh_token"
REFRESH_COOKIE_PATH = "/auth"
COOKIE_SECURE = os.getenv("MAIL_COOKIE_SECURE", "true").lower() != "false"
COOKIE_DOMAIN = os.getenv("MAIL_COOKIE_DOMAIN")

# High-entropy opaque refresh tokens; the ``rt_`` prefix aids on-the-wire
# identification. Stored hashed (sha256) — never in plaintext.
REFRESH_TOKEN_PREFIX = "rt_"


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    address: str
    scopes: list[str]


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


#
# Refresh token helpers
#
def is_interactive_principal(user_agent: MAILUserAgent) -> bool:
    """
    Return True for principals that get a refresh token (users and admins).

    Agents and daemons run unattended and re-authenticate with their
    credentials, so they are deliberately excluded — issuing them refresh
    tokens would only widen the attack surface.
    """

    return isinstance(user_agent.user_agent, MAILUser | MAILAdmin)


def generate_refresh_token() -> str:
    """
    Generate a new high-entropy opaque refresh token (the plaintext returned to
    the client). At least 256 bits of entropy.
    """

    return f"{REFRESH_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_refresh_token(token: str) -> str:
    """
    Hash a refresh token for storage/lookup. SHA-256 is appropriate (and fast)
    because the token is already high-entropy — unlike passwords, it needs no
    slow KDF.
    """

    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token_expiry() -> datetime:
    """
    The absolute expiry for a refresh-token family minted now. Carried forward
    unchanged on rotation (the window does not slide).
    """

    return datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)


def set_refresh_cookie(response: Response, token: str) -> None:
    """
    Set the ``httpOnly`` refresh-token cookie for browser clients.
    """

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        domain=COOKIE_DOMAIN,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    """
    Clear the refresh-token cookie (logout).
    """

    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        domain=COOKIE_DOMAIN,
    )


async def validate_user_agent(
    backend: MAILServerBackend, request: Request
) -> MAILUserAgent:
    user_agent, _token_data = await _authenticate_access_token(
        backend=backend, request=request
    )
    return user_agent


def _insufficient_scope_exception(required_scope: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail=f"access token lacks required scope: {required_scope}",
        headers={
            "WWW-Authenticate": (
                f'Bearer error="insufficient_scope", scope="{required_scope}"'
            )
        },
    )


async def _authenticate_access_token(
    backend: MAILServerBackend, request: Request
) -> tuple[MAILUserAgent, TokenData]:
    """Authenticate a bearer token and return its live principal and claims."""

    credentials_exception = HTTPException(
        status_code=401,
        detail="could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        authorization = request.headers.get("Authorization")
        if authorization is None:
            raise credentials_exception
        scheme, separator, bearer_token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not bearer_token:
            raise credentials_exception
        payload = jwt.decode(jwt=bearer_token, key=SECRET_KEY, algorithms=[ALGORITHM])  # type: ignore
        address = payload.get("sub")
        scope_claim = payload.get("scope", "")
        if not isinstance(address, str) or not address:
            raise credentials_exception
        if not isinstance(scope_claim, str):
            raise credentials_exception
        token_data = TokenData(address=address, scopes=scope_claim.split())
    except InvalidTokenError:
        raise credentials_exception
    try:
        user_agent = await backend.get_user_agent(address)
    except ValueError:
        # The token subject no longer exists (e.g. deleted by an admin).
        raise credentials_exception
    if user_agent is None:
        raise credentials_exception

    return user_agent, token_data


def _require_daemon_scope(
    daemon: MAILDaemon, token_data: TokenData, required_scope: str
) -> None:
    """Require a valid scope in both the JWT grant and the live daemon record."""

    try:
        validate_daemon_scopes(token_data.scopes)
    except ValueError:
        raise _insufficient_scope_exception(required_scope)
    if required_scope not in token_data.scopes or required_scope not in daemon.scopes:
        raise _insufficient_scope_exception(required_scope)


async def validate_daemon(
    backend: MAILServerBackend,
    request: Request,
    *,
    required_scope: str | None = None,
) -> MAILDaemon:
    """
    Ensure that the request user-agent is a valid MAIL daemon.
    """

    user_agent, token_data = await _authenticate_access_token(
        backend=backend, request=request
    )

    if not isinstance(user_agent.user_agent, MAILDaemon):
        raise HTTPException(
            status_code=401,
            detail="could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    daemon = user_agent.user_agent
    if required_scope is not None:
        _require_daemon_scope(daemon, token_data, required_scope)
    return daemon


async def validate_send_authority(
    backend: MAILServerBackend,
    request: Request,
    recipients: Sequence[str],
) -> MAILUserAgent:
    """Apply daemon scopes to sends while retaining ordinary non-daemon sends."""

    user_agent, token_data = await _authenticate_access_token(
        backend=backend, request=request
    )
    daemon = user_agent.user_agent
    if not isinstance(daemon, MAILDaemon):
        return user_agent

    has_remote_recipient = any(
        mail_address_host(recipient).lower() != backend.host.lower()
        for recipient in recipients
    )
    required_scope = "deliver:federate" if has_remote_recipient else "deliver:local"
    _require_daemon_scope(daemon, token_data, required_scope)
    return user_agent


async def validate_admin(backend: MAILServerBackend, request: Request) -> MAILAdmin:
    """
    Ensure that the request user-agent is a valid MAIL admin.
    """

    user_agent = await validate_user_agent(backend=backend, request=request)

    if not isinstance(user_agent.user_agent, MAILAdmin):
        raise HTTPException(
            status_code=401,
            detail="could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_agent.user_agent
