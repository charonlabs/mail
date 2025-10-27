# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import pytest

from mail.stdlib.mcp import (
    mcp_call_tool,
    mcp_get_prompt,
    mcp_list_prompts,
    mcp_list_resources,
    mcp_list_tools,
    mcp_ping,
    mcp_read_resource,
)


class _DummyClient:
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.calls: list[tuple[str, tuple, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def ping(self):
        self.calls.append(("ping", (), {}))
        return "pong"

    async def list_tools(self):
        self.calls.append(("list_tools", (), {}))
        return ["tool-a"]

    async def list_prompts(self):
        self.calls.append(("list_prompts", (), {}))
        return ["prompt-a"]

    async def get_prompt(self, name: str):
        self.calls.append(("get_prompt", (name,), {}))
        return {"name": name}

    async def list_resources(self):
        self.calls.append(("list_resources", (), {}))
        return ["resource-a"]

    async def read_resource(self, uri: str):
        self.calls.append(("read_resource", (uri,), {}))
        return {"uri": uri}

    async def call_tool(self, name: str, payload: dict):
        self.calls.append(("call_tool", (name,), {"payload": payload}))
        return {"output": "ok"}


@pytest.fixture(autouse=True)
def patch_mcp_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(server_url: str) -> _DummyClient:
        return _DummyClient(server_url)

    monkeypatch.setattr("mail.stdlib.mcp.actions.Client", factory)


@pytest.mark.asyncio
async def test_mcp_ping_returns_string() -> None:
    """
    Test that the `mcp_ping` action returns the response string from the MCP server.
    """
    result = await mcp_ping.function({"server_url": "https://mcp"})  # type: ignore[arg-type]
    assert result == "pong"


@pytest.mark.asyncio
async def test_mcp_list_tools() -> None:
    """
    Test that the `mcp_list_tools` action returns the list of tools from the MCP server.
    """
    result = await mcp_list_tools.function({"server_url": "https://mcp"})  # type: ignore[arg-type]
    assert result == "['tool-a']"


@pytest.mark.asyncio
async def test_mcp_get_prompt_and_list_prompts() -> None:
    """
    Test that the `mcp_get_prompt` and `mcp_list_prompts` actions work.
    """
    prompt_result = await mcp_get_prompt.function(
        {"server_url": "https://mcp", "prompt_name": "intro"}
    )  # type: ignore[arg-type]
    prompts = await mcp_list_prompts.function({"server_url": "https://mcp"})  # type: ignore[arg-type]

    assert "'intro'" in prompt_result
    assert "prompt-a" in prompts


@pytest.mark.asyncio
async def test_mcp_resource_helpers() -> None:
    """
    Test that the `mcp_list_resources` and `mcp_read_resource` actions work.
    """
    list_result = await mcp_list_resources.function({"server_url": "https://mcp"})  # type: ignore[arg-type]
    read_result = await mcp_read_resource.function(
        {"server_url": "https://mcp", "resource_uri": "doc://a"}
    )  # type: ignore[arg-type]

    assert "resource-a" in list_result
    assert "doc://a" in read_result


@pytest.mark.asyncio
async def test_mcp_call_tool_passes_payload() -> None:
    """
    Test that the `mcp_call_tool` action passes the payload to the MCP server.
    """
    payload = {
        "server_url": "https://mcp",
        "tool_name": "summarize",
        "tool_input": {"text": "hello"},
    }
    result = await mcp_call_tool.function(payload)  # type: ignore[arg-type]

    assert "ok" in result


@pytest.mark.asyncio
async def test_mcp_action_missing_server_url_returns_error() -> None:
    """
    Test that the `mcp_ping` action returns an error if the server URL is missing.
    """
    result = await mcp_ping.function({})  # type: ignore[arg-type]
    assert result.startswith("Error")
