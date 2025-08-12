"""
Authentication module for ACP server.
"""

import os
import logging

import aiohttp

PROXY_URL = os.getenv("LITELLM_PROXY_API_BASE")

logger = logging.getLogger("acp")


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
    # hit the auth/login endpoint in the proxy
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{PROXY_URL}/auth/login", 
            headers={"Authorization": f"Bearer {api_key}"}
        )
        response.raise_for_status()
        data = await response.json()

        logger.info(f"User authenticated with API key: {api_key[:8]}...")
        return data["token"]
