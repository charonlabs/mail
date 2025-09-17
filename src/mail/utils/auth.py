import logging
import os
from typing import Any

import aiohttp

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
