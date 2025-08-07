"""
Authentication module for ACP server.
"""

import logging
from typing import Optional

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
    # For now, just return the API key as the user token
    # In a real implementation, this would validate against a database
    # and return a proper user token
    
    if not api_key or len(api_key) < 8:
        raise ValueError("Invalid API key")
    
    logger.info(f"User authenticated with API key: {api_key[:8]}...")
    return api_key
