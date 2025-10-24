# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

from fastmcp import Client

from mail import action

MCP_PING_PARAMETERS = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "The URL of the remote MCP server.",
        },
    },
    "required": ["server_url"],
}


@action(
    name="mcp_ping",
    description="Ping a remote MCP server.",
    parameters=MCP_PING_PARAMETERS,
)
async def mcp_ping(args: dict[str, Any]) -> str:
    """
    Ping a remote MCP server.
    """
    server_url = args.get("server_url")

    if server_url is None:
        return "Error: `server_url` is required"
    if not isinstance(server_url, str):
        return "Error: `server_url` must be a string"

    try:
        client = Client(server_url)
        async with client:
            result = await client.ping()
            return str(result)
    except Exception as e:
        return f"Error: {e}"


MCP_LIST_TOOLS_PARAMETERS = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "The URL of the remote MCP server.",
        },
    },
    "required": ["server_url"],
}


@action(
    name="mcp_list_tools",
    description="List the tools on a remote MCP server.",
    parameters=MCP_LIST_TOOLS_PARAMETERS,
)
async def mcp_list_tools(args: dict[str, Any]) -> str:
    """
    List the tools on a remote MCP server.
    """

    server_url = args.get("server_url")

    if server_url is None:
        return "Error: `server_url` is required"
    if not isinstance(server_url, str):
        return "Error: `server_url` must be a string"

    try:
        client = Client(server_url)
        async with client:
            result = await client.list_tools()
            return str(result)
    except Exception as e:
        return f"Error: {e}"


MCP_CALL_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "The URL of the remote MCP server.",
        },
        "tool_name": {
            "type": "string",
            "description": "The name of the tool to call.",
        },
        "tool_input": {
            "type": "object",
            "description": "The input to the tool.",
        },
    },
    "required": ["server_url", "tool_name", "tool_input"],
}


@action(
    name="mcp_call_tool",
    description="Call a tool on a remote MCP server.",
    parameters=MCP_CALL_TOOL_PARAMETERS,
)
async def mcp_call_tool(args: dict[str, Any]) -> str:
    """
    Call a tool on a remote MCP server.
    """
    server_url = args.get("server_url")
    tool_name = args.get("tool_name")
    tool_input = args.get("tool_input")

    if server_url is None:
        return "Error: `server_url` is required"
    if tool_name is None:
        return "Error: `tool_name` is required"
    if tool_input is None:
        return "Error: `tool_input` is required"

    if not isinstance(server_url, str):
        return "Error: `server_url` must be a string"
    if not isinstance(tool_name, str):
        return "Error: `tool_name` must be a string"
    if not isinstance(tool_input, dict):
        return "Error: `tool_input` must be a dictionary"

    try:
        client = Client(server_url)
        async with client:
            result = await client.call_tool(tool_name, tool_input)
            return str(result)
    except Exception as e:
        return f"Error: {e}"


MCP_GET_PROMPT_PARAMETERS = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "The URL of the remote MCP server.",
        },
        "prompt_name": {
            "type": "string",
            "description": "The name of the prompt to get.",
        },
    },
    "required": ["server_url", "prompt_name"],
}


@action(
    name="mcp_get_prompt",
    description="Get a prompt from a remote MCP server.",
    parameters=MCP_GET_PROMPT_PARAMETERS,
)
async def mcp_get_prompt(args: dict[str, Any]) -> str:
    """
    Get a prompt from a remote MCP server.
    """
    server_url = args.get("server_url")
    prompt_name = args.get("prompt_name")

    if server_url is None:
        return "Error: `server_url` is required"
    if prompt_name is None:
        return "Error: `prompt_name` is required"

    if not isinstance(server_url, str):
        return "Error: `server_url` must be a string"
    if not isinstance(prompt_name, str):
        return "Error: `prompt_name` must be a string"

    try:
        client = Client(server_url)
        async with client:
            result = await client.get_prompt(prompt_name)
            return str(result)
    except Exception as e:
        return f"Error: {e}"


@action(
    name="mcp_list_prompts",
    description="List the prompts on a remote MCP server.",
    parameters=MCP_PING_PARAMETERS,
)
async def mcp_list_prompts(args: dict[str, Any]) -> str:
    """
    List the prompts on a remote MCP server.
    """
    server_url = args.get("server_url")

    if server_url is None:
        return "Error: `server_url` is required"
    if not isinstance(server_url, str):
        return "Error: `server_url` must be a string"

    try:
        client = Client(server_url)
        async with client:
            result = await client.list_prompts()
            return str(result)
    except Exception as e:
        return f"Error: {e}"


MCP_READ_RESOURCE_PARAMETERS = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "The URL of the remote MCP server.",
        },
        "resource_uri": {
            "type": "string",
            "description": "The URI of the resource to read.",
        },
    },
    "required": ["server_url", "resource_uri"],
}


@action(
    name="mcp_read_resource",
    description="Read a resource from a remote MCP server.",
    parameters=MCP_READ_RESOURCE_PARAMETERS,
)
async def mcp_read_resource(args: dict[str, Any]) -> str:
    """
    Read a resource from a remote MCP server.
    """
    server_url = args.get("server_url")
    resource_uri = args.get("resource_uri")

    if server_url is None:
        return "Error: `server_url` is required"
    if resource_uri is None:
        return "Error: `resource_uri` is required"

    if not isinstance(server_url, str):
        return "Error: `server_url` must be a string"
    if not isinstance(resource_uri, str):
        return "Error: `resource_uri` must be a string"

    try:
        client = Client(server_url)
        async with client:
            result = await client.read_resource(resource_uri)
            return str(result)
    except Exception as e:
        return f"Error: {e}"


MCP_LIST_RESOURCES_PARAMETERS = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "The URL of the remote MCP server.",
        },
    },
    "required": ["server_url"],
}


@action(
    name="mcp_list_resources",
    description="List the resources on a remote MCP server.",
    parameters=MCP_LIST_RESOURCES_PARAMETERS,
)
async def mcp_list_resources(args: dict[str, Any]) -> str:
    """
    List the resources on a remote MCP server.
    """
    server_url = args.get("server_url")

    if server_url is None:
        return "Error: `server_url` is required"
    if not isinstance(server_url, str):
        return "Error: `server_url` must be a string"

    try:
        client = Client(server_url)
        async with client:
            result = await client.list_resources()
            return str(result)
    except Exception as e:
        return f"Error: {e}"
