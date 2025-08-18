"""
Authentication module for MAIL server.
"""

import os
import logging
from typing import Any

import aiohttp
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

AUTH_ENDPOINT = os.getenv("AUTH_ENDPOINT")
JWT_SECRET = os.getenv("JWT_SECRET")

logger = logging.getLogger("mail")


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

        logger.info(f"user authenticated with API key: '{api_key[:8]}...'")
        return data["token"]
