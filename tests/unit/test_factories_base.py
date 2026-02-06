# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import copy
from typing import Any

import pytest

from mail.factories.base import LiteLLMAgentFunction


def _make_agent() -> LiteLLMAgentFunction:
    return LiteLLMAgentFunction(
        name="agent",
        comm_targets=[],
        tools=[],
        llm="anthropic/claude-sonnet-4-20250514",
        system="",
        use_proxy=False,
        print_llm_streams=False,
    )


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _iter_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def _assert_no_parsed_output(value: Any) -> None:
    for item in _iter_dicts(value):
        assert "parsed_output" not in item


def _assert_text_blocks_are_strings(value: Any) -> None:
    for item in _iter_dicts(value):
        if item.get("type") == "text":
            assert isinstance(item.get("text"), str)


class _DummyBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text

    def model_dump(self) -> dict[str, Any]:
        # Simulate upstream typed payload shape that can include invalid nested fields.
        return {
            "type": "text",
            "text": {
                "value": self.text,
                "parsed_output": {"debug": True},
            },
        }


class _DummyMessageResponse:
    def __init__(self, content: list[_DummyBlock], stop_reason: str):
        self.content = content
        self.stop_reason = stop_reason


class _DummyStream:
    def __init__(self, final_message: _DummyMessageResponse):
        self._final_message = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def get_final_message(self) -> _DummyMessageResponse:
        return self._final_message


class _DummyMessagesCreateAPI:
    def __init__(self, responses: list[_DummyMessageResponse]):
        self.calls: list[dict[str, Any]] = []
        self._responses = responses

    async def create(self, **kwargs: Any) -> _DummyMessageResponse:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _DummyMessagesStreamAPI:
    def __init__(self, final_messages: list[_DummyMessageResponse]):
        self.calls: list[dict[str, Any]] = []
        self._final_messages = final_messages

    def stream(self, **kwargs: Any) -> _DummyStream:
        self.calls.append(kwargs)
        return _DummyStream(self._final_messages.pop(0))


class _DummyAnthropicClient:
    def __init__(self, messages_api: Any):
        self.messages = messages_api


def test_sanitize_anthropic_payload_is_idempotent_and_non_mutating() -> None:
    agent = _make_agent()
    payload = {
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": {
                    "value": "hello",
                    "parsed_output": {"x": 1},
                },
            },
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "search",
                "input": {"query": "q", "parsed_output": {"y": 2}},
            },
        ],
    }
    original = copy.deepcopy(payload)

    once = agent._sanitize_anthropic_payload(payload)
    twice = agent._sanitize_anthropic_payload(once)

    assert payload == original
    assert once == twice
    _assert_no_parsed_output(once)
    _assert_text_blocks_are_strings(once)


def test_convert_messages_to_anthropic_format_sanitizes_typed_messages() -> None:
    agent = _make_agent()
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": {"value": "assistant text", "parsed_output": {"a": 1}},
                }
            ],
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": None}],
        },
        {
            "role": "tool",
            "tool_call_id": "call_2",
            "content": {"ok": True, "parsed_output": {"b": 2}},
        },
    ]
    original = copy.deepcopy(messages)

    converted = agent._convert_messages_to_anthropic_format(messages)

    assert messages == original
    _assert_no_parsed_output(converted)
    _assert_text_blocks_are_strings(converted)


@pytest.mark.asyncio
async def test_run_completions_anthropic_native_sanitizes_pause_turn_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _make_agent()
    messages_api = _DummyMessagesCreateAPI(
        [
            _DummyMessageResponse([_DummyBlock("part one")], "pause_turn"),
            _DummyMessageResponse([_DummyBlock("part two")], "end_turn"),
        ]
    )
    client = _DummyAnthropicClient(messages_api)

    monkeypatch.setattr("mail.factories.base.anthropic.AsyncAnthropic", lambda: client)
    monkeypatch.setattr("mail.factories.base.wrap_anthropic", lambda c: c)

    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": {"value": "prior", "parsed_output": {"x": 1}}}
            ],
        },
    ]

    content, tool_calls = await agent._run_completions_anthropic_native(
        messages=messages,
        agent_tools=[],
        tool_choice="auto",
    )

    assert content == "part onepart two"
    assert tool_calls
    assert len(messages_api.calls) == 2
    for call in messages_api.calls:
        _assert_no_parsed_output(call["messages"])
        _assert_text_blocks_are_strings(call["messages"])


@pytest.mark.asyncio
async def test_stream_completions_anthropic_native_sanitizes_pause_turn_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _make_agent()
    messages_api = _DummyMessagesStreamAPI(
        [
            _DummyMessageResponse([_DummyBlock("part one")], "pause_turn"),
            _DummyMessageResponse([_DummyBlock("part two")], "end_turn"),
        ]
    )
    client = _DummyAnthropicClient(messages_api)

    monkeypatch.setattr("mail.factories.base.anthropic.AsyncAnthropic", lambda: client)
    monkeypatch.setattr("mail.factories.base.wrap_anthropic", lambda c: c)

    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": {"value": "prior", "parsed_output": {"x": 1}}}
            ],
        },
    ]

    content, tool_calls = await agent._stream_completions_anthropic_native(
        messages=messages,
        agent_tools=[],
        tool_choice="auto",
    )

    assert content == "part onepart two"
    assert tool_calls
    assert len(messages_api.calls) == 2
    for call in messages_api.calls:
        _assert_no_parsed_output(call["messages"])
        _assert_text_blocks_are_strings(call["messages"])
