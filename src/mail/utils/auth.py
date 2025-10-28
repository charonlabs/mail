# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import logging
import os
from typing import Any

import aiohttp
from fastapi import HTTPException, Request

JWT_SECRET = os.getenv("JWT_SECRET")

logger = logging.getLogger("mail.auth")


async def check_auth_endpoints() -> None:
    """
    Check if the auth endpoints are set.
    This is necessary for the server to start.
    """
    AUTH_ENDPOINTS = ["AUTH_ENDPOINT", "TOKEN_INFO_ENDPOINT"]
    for endpoint in AUTH_ENDPOINTS:
        if endpoint not in os.environ or os.getenv(endpoint) is None:
            logger.error(f"required environment variable '{endpoint}' is not set")
            raise Exception(f"required environment variable '{endpoint}' is not set")


def extract_token(request: Request) -> str:
    """
    Extract the token from the request.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    else:
        raise HTTPException(status_code=401, detail="invalid API key format")


async def login(api_key: str) -> str:
    """
    Authenticate a user with an API key.

    Args:
        api_key: The API key to validate

    Returns:
        A user token if authentication is successful

    Raises:
        ValueError: If the API key is invalid
    """
    await check_auth_endpoints()
    AUTH_ENDPOINT = os.getenv("AUTH_ENDPOINT")

    # hit the login endpoint in the auth service
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{AUTH_ENDPOINT}", headers={"Authorization": f"Bearer {api_key}"}
        )
        if response.status == 200:
            data = await response.json()
            logger.info(
                f"[[green]{api_key[:8]}...[/green]] user or agent authenticated with API key"
            )
            return data["token"]
        elif response.status == 401:
            logger.warning(f"invalid API key: '{api_key}'")
            raise HTTPException(status_code=401, detail="invalid API key")
        else:
            logger.error(
                f"failed to authenticate user or agent with API key: '{api_key}': '{response.status}'"
            )
            raise HTTPException(
                status_code=500,
                detail="failed to authenticate user or agent with API key",
            )


async def get_token_info(token: str) -> dict[str, Any]:
    """
    Get information about a JWT.
    """
    await check_auth_endpoints()
    TOKEN_INFO_ENDPOINT = os.getenv("TOKEN_INFO_ENDPOINT")

    async with aiohttp.ClientSession() as session:
        response = await session.get(
            f"{TOKEN_INFO_ENDPOINT}", headers={"Authorization": f"Bearer {token}"}
        )
        if response.status == 200:
            data = await response.json()
            return data
        elif response.status == 401:
            logger.warning(f"invalid token: '{token}'")
            raise HTTPException(status_code=401, detail="invalid token")
        else:
            logger.error(f"failed to get token info: '{token}': '{response.status}'")
            raise HTTPException(status_code=500, detail="failed to get token info")


async def caller_is_role(
    request: Request, role: str, raise_on_false: bool = True
) -> bool:
    """
    Check if the caller is a specific role.
    """
    token = request.headers.get("Authorization")
    if token is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    if token.startswith("Bearer "):
        token = token.split(" ")[1]
    else:
        logger.warning("invalid API key format: missing 'Bearer' prefix")
        if raise_on_false:
            raise HTTPException(status_code=401, detail="invalid API key format")
        return False

    # login to the auth service
    jwt = await login(token)

    token_info = await get_token_info(jwt)
    if token_info["role"] != role:
        if raise_on_false:
            logger.warning(f"invalid role: '{token_info['role']}' != '{role}'")
            raise HTTPException(status_code=401, detail="invalid role")
        return False

    return True


async def caller_is_admin(request: Request, raise_on_false: bool = True) -> bool:
    """
    Check if the caller is an `admin`.
    """
    return await caller_is_role(request, "admin", raise_on_false)


async def caller_is_user(request: Request, raise_on_false: bool = True) -> bool:
    """
    Check if the caller is a `user`.
    """
    return await caller_is_role(request, "user", raise_on_false)


async def caller_is_admin_or_user(request: Request) -> bool:
    """
    Check if the caller is an `admin` or a `user`.
    """
    is_admin = await caller_is_admin(request, raise_on_false=False)
    is_user = await caller_is_user(request, raise_on_false=False)
    if is_admin or is_user:
        return True

    logger.warning("invalid role: caller is not admin or user")
    raise HTTPException(status_code=401, detail="invalid role")


async def caller_is_agent(request: Request, raise_on_false: bool = True) -> bool:
    """
    Check if the caller is an `agent`.
    """
    return await caller_is_role(request, "agent", raise_on_false)


async def extract_token_info(request: Request) -> dict[str, Any]:
    """
    Extract the token info from the request.
    """
    token = request.headers.get("Authorization")

    if token is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")
    if token.startswith("Bearer "):
        token = token.split(" ")[1]
    else:
        logger.warning("invalid API key format: missing 'Bearer' prefix")
        raise HTTPException(status_code=401, detail="invalid API key format")

    # login to the auth service
    jwt = await login(token)

    return await get_token_info(jwt)


def require_debug(request: Request) -> None:
    """
    Require the debug mode to be enabled.
    """
    if not request.app.state.debug:
        logger.warning("debug mode is not enabled")
        raise HTTPException(status_code=404, detail="Not found")
