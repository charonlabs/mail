# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

import pytest

from mail.core.tools import (
    convert_call_to_mail_message,
    create_mail_tools,
    create_request_tool,
    create_supervisor_tools,
    create_task_complete_tool,
)
from mail.factories.base import AgentToolCall


def _call(name: str, args: dict[str, Any]) -> AgentToolCall:
    return AgentToolCall(
        tool_name=name,
        tool_args=args,
        tool_call_id="t1",
        completion={"role": "assistant", "content": "ok"},
    )


def test_create_request_tool_completions_enforces_enum():
    """
    Test that `create_request_tool` works as expected for completions.
    """
    tool = create_request_tool(
        ["analyst", "helper"], enable_interswarm=False, style="completions"
    )
    assert tool["type"] == "function"
    assert "function" in tool and "parameters" in tool["function"]
    props = tool["function"]["parameters"]["properties"]
    assert set(["target", "subject", "message"]).issubset(set(props.keys()))
    assert props["target"]["enum"] == ["analyst", "helper"]


def test_create_request_tool_responses_interswarm_description():
    """
    Test that `create_request_tool` works as expected for responses.
    """
    tool = create_request_tool(["analyst"], enable_interswarm=True, style="responses")
    assert tool["type"] == "function"
    assert tool["name"] == "send_request"
    props = tool["parameters"]["properties"]
    assert "agent-name@swarm-name" in props["target"]["description"]
    # In interswarm mode we should not restrict enum values
    assert "enum" not in props["target"]


def test_create_supervisor_tools_contains_task_complete_conditionally():
    """
    Test that `create_supervisor_tools` works as expected.
    """
    tools_without_complete = create_supervisor_tools(
        ["analyst"], can_complete_tasks=False
    )
    names = [t.get("function", t).get("name") for t in tools_without_complete]
    assert "task_complete" not in names

    tools_with_complete = create_supervisor_tools(["analyst"], can_complete_tasks=True)
    names2 = [t.get("function", t).get("name") for t in tools_with_complete]
    assert "task_complete" in names2


def test_create_mail_tools_set():
    """
    Test that `create_mail_tools` works as expected.
    """
    tools = create_mail_tools(["analyst", "helper"])  # default style: completions
    names = [t["function"]["name"] for t in tools]
    # Expected tools for standard agents
    assert set(names) == {
        "send_request",
        "send_response",
        "acknowledge_broadcast",
        "ignore_broadcast",
    }


def test_create_task_complete_tool_shape():
    """
    Test that `create_task_complete_tool` works as expected.
    """
    tool = create_task_complete_tool(style="responses")
    assert tool["type"] == "function"
    assert tool["name"] == "task_complete"
    props = tool["parameters"]["properties"]
    assert list(props.keys()) == ["finish_message"]


def test_convert_call_unknown_tool_raises():
    """
    Test that `convert_call_to_mail_message` raises an error for an unknown tool.
    """
    with pytest.raises(ValueError):
        convert_call_to_mail_message(_call("not_a_tool", {}), sender="a", task_id="t")
