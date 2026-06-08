# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

import aiohttp

from mail import action

HTTP_GET_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL to GET.",
        },
        "headers": {
            "type": "object",
            "description": "The headers to send with the request.",
            "optional": True,
        },
    },
    "required": ["url"],
}


@action(
    name="http_get",
    description="Get a URL via HTTP.",
    parameters=HTTP_GET_PARAMETERS,
)
async def http_get(args: dict[str, Any]) -> str:
    """
    Get a URL via HTTP.
    """
    url = args.get("url")
    if url is None:
        return "Error: `url` is required"
    if not isinstance(url, str):
        return "Error: `url` must be a string"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text()
    except Exception as e:
        return f"Error: {e}"


HTTP_POST_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL to POST to.",
        },
        "headers": {
            "type": "object",
            "description": "The headers to send with the request.",
        },
        "body": {
            "type": "object",
            "description": "The body to send with the request.",
        },
    },
    "required": ["url", "headers", "body"],
}


@action(
    name="http_post",
    description="Post to a URL via HTTP.",
    parameters=HTTP_POST_PARAMETERS,
)
async def http_post(args: dict[str, Any]) -> str:
    """
    Post to a URL via HTTP.
    """
    url = args.get("url")
    headers = args.get("headers")
    body = args.get("body")

    if url is None:
        return "Error: `url` is required"
    if headers is None:
        return "Error: `headers` is required"
    if body is None:
        return "Error: `body` is required"

    if not isinstance(url, str):
        return "Error: `url` must be a string"
    if not isinstance(headers, dict):
        return "Error: `headers` must be a dictionary"
    if not isinstance(body, dict):
        return "Error: `body` must be a dictionary"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as response:
                return await response.text()
    except Exception as e:
        return f"Error: {e}"


HTTP_PUT_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL to PUT to.",
        },
        "headers": {
            "type": "object",
            "description": "The headers to send with the request.",
        },
        "body": {
            "type": "object",
            "description": "The body to send with the request.",
        },
    },
    "required": ["url", "headers", "body"],
}


@action(
    name="http_put",
    description="Put to a URL via HTTP.",
    parameters=HTTP_PUT_PARAMETERS,
)
async def http_put(args: dict[str, Any]) -> str:
    """
    Put to a URL via HTTP.
    """
    url = args.get("url")
    headers = args.get("headers")
    body = args.get("body")

    if url is None:
        return "Error: `url` is required"
    if headers is None:
        return "Error: `headers` is required"
    if body is None:
        return "Error: `body` is required"

    if not isinstance(url, str):
        return "Error: `url` must be a string"
    if not isinstance(headers, dict):
        return "Error: `headers` must be a dictionary"
    if not isinstance(body, dict):
        return "Error: `body` must be a dictionary"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, json=body) as response:
                return await response.text()
    except Exception as e:
        return f"Error: {e}"


HTTP_DELETE_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL to DELETE.",
        },
        "headers": {
            "type": "object",
            "description": "The headers to send with the request.",
            "optional": True,
        },
    },
    "required": ["url"],
}


@action(
    name="http_delete",
    description="Delete a URL via HTTP.",
    parameters=HTTP_DELETE_PARAMETERS,
)
async def http_delete(args: dict[str, Any]) -> str:
    """
    Delete a URL via HTTP.
    """
    url = args.get("url")
    if url is None:
        return "Error: `url` is required"
    if not isinstance(url, str):
        return "Error: `url` must be a string"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url) as response:
                return await response.text()
    except Exception as e:
        return f"Error: {e}"


HTTP_PATCH_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL to PATCH.",
        },
        "headers": {
            "type": "object",
            "description": "The headers to send with the request.",
            "optional": True,
        },
        "body": {
            "type": "object",
            "description": "The body to send with the request.",
        },
    },
    "required": ["url", "body"],
}


@action(
    name="http_patch",
    description="Patch a URL via HTTP.",
    parameters=HTTP_PATCH_PARAMETERS,
)
async def http_patch(args: dict[str, Any]) -> str:
    """
    Patch a URL via HTTP.
    """
    url = args.get("url")
    headers = args.get("headers")
    body = args.get("body")

    if url is None:
        return "Error: `url` is required"
    if body is None:
        return "Error: `body` is required"

    if not isinstance(url, str):
        return "Error: `url` must be a string"
    if not isinstance(body, dict):
        return "Error: `body` must be a dictionary"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, json=body) as response:
                return await response.text()
    except Exception as e:
        return f"Error: {e}"


HTTP_HEAD_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL to HEAD.",
        },
        "headers": {
            "type": "object",
            "description": "The headers to send with the request.",
            "optional": True,
        },
    },
    "required": ["url"],
}


@action(
    name="http_head",
    description="Head a URL via HTTP.",
    parameters=HTTP_HEAD_PARAMETERS,
)
async def http_head(args: dict[str, Any]) -> str:
    """
    Head a URL via HTTP.
    """
    url = args.get("url")
    headers = args.get("headers")

    if url is None:
        return "Error: `url` is required"
    if not isinstance(url, str):
        return "Error: `url` must be a string"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, headers=headers) as response:
                return await response.text()
    except Exception as e:
        return f"Error: {e}"


HTTP_OPTIONS_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL to OPTIONS.",
        },
        "headers": {
            "type": "object",
            "description": "The headers to send with the request.",
            "optional": True,
        },
    },
    "required": ["url"],
}


@action(
    name="http_options",
    description="Options a URL via HTTP.",
    parameters=HTTP_OPTIONS_PARAMETERS,
)
async def http_options(args: dict[str, Any]) -> str:
    """
    Options a URL via HTTP.
    """
    url = args.get("url")
    headers = args.get("headers")

    if url is None:
        return "Error: `url` is required"
    if not isinstance(url, str):
        return "Error: `url` must be a string"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.options(url, headers=headers) as response:
                return await response.text()
    except Exception as e:
        return f"Error: {e}"
