# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
from types import SimpleNamespace
from typing import Any

import pytest

from mail.stdlib.openai import (
    OpenAIChatCompletionsAgentFunction,
    OpenAIChatCompletionsSupervisorFunction,
    OpenAIResponsesAgentFunction,
)


class DummyToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]):
        self.id = call_id
        self.function = SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments),
        )


class DummyMessage:
    def __init__(
        self, content: str | None, tool_calls: list[DummyToolCall] | None = None
    ):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none: bool = True) -> dict[str, Any]:
        data = {"role": "assistant", "content": self.content}
        if exclude_none and self.content is None:
            data["content"] = None
        return data


class DummyChatResponse:
    def __init__(self, message: DummyMessage):
        self.choices = [SimpleNamespace(message=message)]


class DummyResponsesResponse:
    def __init__(self, output: list[dict[str, Any]]):
        self.output = output

    def model_dump(self) -> dict[str, Any]:
        return {"output": self.output}


@pytest.fixture(autouse=True)
def patch_async_openai(monkeypatch: pytest.MonkeyPatch):
    instances: list["DummyAsyncOpenAI"] = []

    class DummyAsyncOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat_requests: list[dict[str, Any]] = []
            self.responses_requests: list[dict[str, Any]] = []
            self.chat_response: DummyChatResponse | None = None
            self.responses_response: DummyResponsesResponse | None = None

            async def chat_create(**request_kwargs):
                self.chat_requests.append(request_kwargs)
                assert self.chat_response is not None, "chat_response not set"
                return self.chat_response

            async def responses_create(**request_kwargs):
                self.responses_requests.append(request_kwargs)
                assert self.responses_response is not None, "responses_response not set"
                return self.responses_response

            self.chat = SimpleNamespace(completions=SimpleNamespace(create=chat_create))
            self.responses = SimpleNamespace(create=responses_create)
            instances.append(self)

    monkeypatch.setattr(
        "mail.stdlib.openai.agents.openai.AsyncOpenAI", DummyAsyncOpenAI
    )
    return instances


@pytest.mark.asyncio
async def test_chat_completions_agent_returns_tool_calls(patch_async_openai):
    """
    Test that the chat completions agent returns tool calls.
    """
    tools = [
        {
            "name": "lookup_weather",
            "description": "Lookup the current weather.",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    agent = OpenAIChatCompletionsAgentFunction(
        name="assistant",
        comm_targets=["supervisor"],
        model="gpt-4o-mini",
        tools=tools,
    )

    client = patch_async_openai[-1]
    tool_call = DummyToolCall("call_1", "lookup_weather", {"location": "Boston"})
    client.chat_response = DummyChatResponse(DummyMessage("Sure!", [tool_call]))

    content, tool_calls = await agent(
        messages=[{"role": "user", "content": "What's the weather?"}]
    )

    assert content == "Sure!"
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "lookup_weather"
    assert tool_calls[0].tool_args == {"location": "Boston"}
    assert tool_calls[0].completion  # completion payload stored

    request = client.chat_requests[0]
    assert request["model"] == "gpt-4o-mini"
    assert request["messages"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_responses_agent_returns_text_and_calls(patch_async_openai):
    """
    Test that the responses agent returns text and tool calls.
    """
    tools = [
        {
            "name": "fetch_data",
            "description": "Fetch structured data.",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    agent = OpenAIResponsesAgentFunction(
        name="assistant",
        comm_targets=["supervisor"],
        model="gpt-4.1",
        tools=tools,
    )

    client = patch_async_openai[-1]
    client.responses_response = DummyResponsesResponse(
        output=[
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Working on it..."}],
            },
            {
                "type": "custom_tool_call",
                "call_id": "call_2",
                "name": "fetch_data",
                "input": json.dumps({"query": "status"}),
            },
        ]
    )

    content, tool_calls = await agent(
        messages=[{"role": "user", "content": "Check status"}]
    )

    assert content == "Working on it..."
    assert tool_calls[0].tool_name == "fetch_data"
    assert tool_calls[0].tool_args == {"query": "status"}
    assert tool_calls[0].responses  # full responses payload stored

    request = client.responses_requests[0]
    assert request["model"] == "gpt-4.1"
    assert request["tools"][0]["function"]["name"] == "fetch_data"


def test_supervisor_includes_supervisor_tools(patch_async_openai):
    """
    Test that the supervisor includes supervisor tools.
    """
    tools = [
        {
            "name": "lookup_weather",
            "description": "Lookup the current weather.",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    supervisor = OpenAIChatCompletionsSupervisorFunction(
        name="supervisor",
        comm_targets=["assistant"],
        model="gpt-4o-mini",
        tools=tools,
        enable_entrypoint=True,
        enable_interswarm=False,
    )

    def extract_name(tool: dict[str, Any]) -> str | None:
        if "name" in tool:
            return tool["name"]
        if isinstance(tool.get("function"), dict):
            return tool["function"].get("name")
        return None

    tool_names = {
        name
        for name in (extract_name(tool) for tool in supervisor.supervisor_fn.tools)
        if name
    }
    # Supervisor helpers should be available alongside user tools
    assert "lookup_weather" in tool_names
    assert {
        "send_broadcast",
        "send_interrupt",
        "task_complete",
    }.intersection(tool_names)
