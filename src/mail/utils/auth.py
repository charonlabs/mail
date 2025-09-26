# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import logging
import os
from typing import Any

import aiohttp
from fastapi import HTTPException, Request

AUTH_ENDPOINT = os.getenv("AUTH_ENDPOINT")
TOKEN_INFO_ENDPOINT = os.getenv("TOKEN_INFO_ENDPOINT")
JWT_SECRET = os.getenv("JWT_SECRET")

logger = logging.getLogger("mail.auth")


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
    # hit the login endpoint in the auth service
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{AUTH_ENDPOINT}", headers={"Authorization": f"Bearer {api_key}"}
        )
        response.raise_for_status()
        data = await response.json()

        logger.info(f"user or agent authenticated with API key: '{api_key[:8]}...'")
        return data["token"]


async def get_token_info(token: str) -> dict[str, Any]:
    """
    Get information about a JWT.
    """
    async with aiohttp.ClientSession() as session:
        response = await session.get(
            f"{TOKEN_INFO_ENDPOINT}", headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        return await response.json()


async def caller_is_role(request: Request, role: str) -> bool:
    """
    Check if the caller is a specific role.
    """
    token = request.headers.get("Authorization")
    if token is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    if token.startswith("Bearer "):
        token = token.split(" ")[1]

    # login to the auth service
    jwt = await login(token)

    token_info = await get_token_info(jwt)
    if token_info["role"] != role:
        logger.warning(f"invalid role: '{token_info['role']}' != '{role}'")
        return False

    return True


async def caller_is_admin(request: Request) -> bool:
    """
    Check if the caller is an `admin`.
    """
    return await caller_is_role(request, "admin")


async def caller_is_user(request: Request) -> bool:
    """
    Check if the caller is a `user`.
    """
    return await caller_is_role(request, "user")


async def caller_is_admin_or_user(request: Request) -> bool:
    """
    Check if the caller is an `admin` or a `user`.
    """
    is_admin = await caller_is_admin(request)
    is_user = await caller_is_user(request)
    if is_admin or is_user:
        return True

    logger.warning("invalid role: 'admin' or 'user' is not admin or user")
    raise HTTPException(status_code=401, detail="invalid role")


async def caller_is_agent(request: Request) -> bool:
    """
    Check if the caller is an `agent`.
    """
    return await caller_is_role(request, "agent")


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

    # login to the auth service
    jwt = await login(token)

    return await get_token_info(jwt)


def generate_user_id(token_info: dict[str, Any]) -> str:
    """
    Generate a user ID from a token info dictionary.
    """
    user_role = token_info["role"]
    user_id = token_info["id"]
    return f"{user_role}_{user_id}"


def generate_agent_id(token_info: dict[str, Any]) -> str:
    """
    Generate an agent ID from a token info dictionary.
    """
    agent_id = token_info["id"]
    return f"swarm_{agent_id}"
