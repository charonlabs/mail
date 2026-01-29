# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

import aiohttp

from mail import action

SWARM_URL_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL of the remote swarm.",
        },
    },
    "required": ["url"],
}


@action(
    name="ping_swarm",
    description="Check if a remote URL hosts an active MAIL swarm.",
    parameters=SWARM_URL_PARAMETERS,
)
async def ping_swarm(args: dict[str, Any]) -> str:
    """
    Check if a remote URL is a valid, active MAIL swarm.

    Args:
        url: The URL of the remote swarm.

    Returns:
        "pong" if the URL represents an active MAIL swarm, otherwise an error message.
    """
    url = args.get("url")
    if url is None:
        return "Error: `url` is required"
    if not isinstance(url, str):
        return "Error: `url` must be a string"

    # attempt to ping (`GET /`) the remote swarm
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    if await _is_valid_mail_root_response(response):
                        return "pong"
                    else:
                        return "Error: remote URL is not a valid MAIL swarm"
                else:
                    return f"Error: remote URL returned status code {response.status}"
    except Exception as e:
        return f"Error: {e}"


@action(
    name="get_swarm_health",
    description="Get the health status of a remote MAIL swarm.",
    parameters=SWARM_URL_PARAMETERS,
)
async def get_swarm_health(args: dict[str, Any]) -> str:
    """
    Get the health of a remote MAIL swarm.

    Args:
        url: The URL of the remote swarm.

    Returns:
        The health status string of the swarm, otherwise an error message.
    """
    url = args.get("url")
    if url is None:
        return "Error: `url` is required"
    if not isinstance(url, str):
        return "Error: `url` must be a string"

    # attempt to `GET /health` on the remote swarm
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url + "/health") as response:
                if response.status == 200:
                    if await _is_valid_mail_health_response(response):
                        json = await response.json()
                        return json.get("status")
                    else:
                        return "Error: remote URL is not a valid MAIL swarm"
                else:
                    return f"Error: remote URL returned status code {response.status}"
    except Exception as e:
        return f"Error: {e}"


@action(
    name="get_swarm_registry",
    description="Fetch the registry listing for a remote MAIL swarm.",
    parameters=SWARM_URL_PARAMETERS,
)
async def get_swarm_registry(args: dict[str, Any]) -> str:
    """
    Get the registry of the remote MAIL swarm.

    Args:
        url: The URL of the remote swarm.

    Returns:
        The registry of the remote MAIL swarm, otherwise an error message.
    """
    url = args.get("url")
    if url is None:
        return "Error: `url` is required"
    if not isinstance(url, str):
        return "Error: `url` must be a string"

    # attempt to `GET /swarms` on the remote swarm
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url + "/swarms") as response:
                if response.status == 200:
                    if await _is_valid_mail_swarms_response(response):
                        return await _swarm_registry_response_str(response)
                    else:
                        return "Error: remote URL is not a valid MAIL swarm"
                else:
                    return f"Error: remote URL returned status code {response.status}"
    except Exception as e:
        return f"Error: {e}"


async def _is_valid_mail_root_response(response: aiohttp.ClientResponse) -> bool:
    """
    Based on the response to `GET /`, determine if the remote URL is in fact a valid MAIL swarm.
    """
    json = await response.json()
    name = json.get("name")
    swarm = json.get("swarm")
    status = json.get("status")

    if not name or not swarm or not status:
        return False
    if (
        not isinstance(name, str)
        or not isinstance(swarm, dict)
        or not isinstance(status, str)
    ):
        return False
    if name != "mail" or status != "running":
        return False
    if not isinstance(swarm.get("name"), str) or not isinstance(
        swarm.get("entrypoint"), str
    ):
        return False

    return True


async def _is_valid_mail_health_response(response: aiohttp.ClientResponse) -> bool:
    """
    Based on the response to `GET /health`, determine if the remote URL is in fact a valid MAIL swarm.
    """
    json = await response.json()
    status = json.get("status")
    swarm_name = json.get("swarm_name")

    if not status or not swarm_name:
        return False
    if not isinstance(status, str) or not isinstance(swarm_name, str):
        return False

    return True


async def _is_valid_mail_swarms_response(response: aiohttp.ClientResponse) -> bool:
    """
    Based on the response to `GET /swarms`, determine if the remote URL is in fact a valid MAIL swarm.
    """
    json = await response.json()
    swarms = json.get("swarms")

    if not swarms:
        return False
    if not isinstance(swarms, list):
        return False
    for swarm in swarms:
        if not isinstance(swarm, dict):
            return False
        if not isinstance(swarm.get("swarm_name"), str) or not isinstance(
            swarm.get("base_url"), str
        ):
            return False

    return True


async def _swarm_registry_response_str(response: aiohttp.ClientResponse) -> str:
    """
    Convert the response to `GET /swarms` to a string representation of the registry.
    """
    json = await response.json()
    swarms = json.get("swarms")

    if not swarms:
        return "No swarms found"
    if not isinstance(swarms, list):
        return "Error: `swarms` is not a list"

    return "\n".join([f"{swarm['swarm_name']}@{swarm['base_url']}" for swarm in swarms])
