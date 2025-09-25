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
    Get information about a token.
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

    token_info = await get_token_info(token)
    if token_info["role"] != role:
        logger.warning(f"invalid role: '{token_info['role']}' != '{role}'")
        raise HTTPException(status_code=401, detail="invalid role")

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
    token_header = request.headers.get("Authorization")
    if token_header is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    # Preserve historical behavior expected by tests: a non-Bearer header
    # should be treated as unauthorized ("invalid role").
    if not token_header.startswith("Bearer "):
        logger.warning("invalid role: header missing 'Bearer ' prefix")
        raise HTTPException(status_code=401, detail="invalid role")

    token = token_header.split(" ")[1]
    token_info = await get_token_info(token)
    role = token_info.get("role")
    if role in ("admin", "user"):
        return True

    logger.warning(f"invalid role: '{role}' is not admin or user")
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

    return await get_token_info(token)


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
