# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import asyncio
import json

import pytest

from mail.core import (
    AgentCore,
    MAILMessage,
    MAILRequest,
    MAILRuntime,
    create_agent_address,
    create_user_address,
)


@pytest.mark.asyncio
async def test_submit_and_wait_resolves_on_task_complete() -> None:
    """
    Test that `submit_and_wait` resolves on `task_complete`.
    """

    async def stub_agent(history, tool_choice):  # noqa: ARG001
        from mail.core.tools import AgentToolCall

        call = AgentToolCall(
            tool_name="task_complete",
            tool_args={"finish_message": "All good"},
            tool_call_id="c1",
            completion={"role": "assistant", "content": "ok"},
        )
        return None, [call]

    mail = MAILRuntime(
        agents={
            "supervisor": AgentCore(
                function=stub_agent,
                comm_targets=["supervisor"],
                enable_entrypoint=True,
                enable_interswarm=False,
                can_complete_tasks=True,
            )
        },
        actions={},
        user_id="user-1",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
        swarm_registry=None,
        enable_interswarm=False,
    )

    msg: MAILMessage = MAILMessage(
        id="m1",
        timestamp="2024-01-01T00:00:00Z",
        message=MAILRequest(
            task_id="t1",
            request_id="r1",
            sender=create_user_address("user-1"),
            recipient=create_agent_address("supervisor"),
            subject="Hello",
            body="Do the thing",
            sender_swarm=None,
            recipient_swarm=None,
            routing_info=None,
        ),
        msg_type="request",
    )

    # Start continuous processing to consume the queue
    loop_task = asyncio.create_task(mail.run_continuous())
    try:
        # Give the loop a tick to start
        await asyncio.sleep(0)

        # Submit and wait should resolve quickly from stub agent
        result = await asyncio.wait_for(
            mail.submit_and_wait(msg, timeout=2.0), timeout=3.0
        )
    finally:
        await mail.shutdown()
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
    assert result["msg_type"] == "broadcast_complete"
    assert result["message"]["body"] == "All good"


@pytest.mark.asyncio
async def test_breakpoint_tool_triggers_task_complete() -> None:
    """
    Ensure breakpoint tools complete the task and surface the tool call.
    """

    async def breakpoint_agent(history, tool_choice):  # noqa: ARG001
        from mail.core.tools import AgentToolCall

        call = AgentToolCall(
            tool_name="pause_for_debug",
            tool_args={"note": "pausing"},
            tool_call_id="bp-1",
            responses=[
                {
                    "arguments": '{"note": "pausing"}',
                    "call_id": "bp-1",
                    "name": "pause_for_debug",
                    "type": "function_call",
                    "id": "fc_0bae822d2db78dbb0068ed566096b4819cb9cf976153d0e314",
                    "status": "completed",
                }
            ],
        )
        return None, [call]

    mail = MAILRuntime(
        agents={
            "supervisor": AgentCore(
                function=breakpoint_agent,
                comm_targets=["supervisor"],
                enable_entrypoint=True,
                enable_interswarm=False,
                can_complete_tasks=True,
            )
        },
        actions={},
        user_id="user-1",
        user_role="user",
        swarm_name="example",
        swarm_registry=None,
        enable_interswarm=False,
        entrypoint="supervisor",
        breakpoint_tools=["pause_for_debug"],
    )

    msg: MAILMessage = MAILMessage(
        id="m1",
        timestamp="2024-01-01T00:00:00Z",
        message=MAILRequest(
            task_id="t-break",
            request_id="r-break",
            sender=create_user_address("user-1"),
            recipient=create_agent_address("supervisor"),
            subject="Pause",
            body="hit breakpoint",
            sender_swarm=None,
            recipient_swarm=None,
            routing_info=None,
        ),
        msg_type="request",
    )

    loop_task = asyncio.create_task(mail.run_continuous())
    try:
        await asyncio.sleep(0)

        result = await asyncio.wait_for(
            mail.submit_and_wait(msg, timeout=2.0), timeout=3.0
        )
    finally:
        await mail.shutdown()
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    assert result["msg_type"] == "broadcast_complete"
    assert result["message"]["subject"] == "::breakpoint_tool_call::"

    payload = json.loads(result["message"]["body"])
    assert payload[0]["name"] == "pause_for_debug"
    assert payload[0]["arguments"] == '{"note": "pausing"}'
    assert payload[0]["call_id"] == "bp-1"


@pytest.mark.asyncio
async def test_breakpoint_tool_triggers_task_complete_anthropic() -> None:
    """
    Ensure Anthropic tool_use blocks are normalized to function_call output.
    """

    async def breakpoint_agent(history, tool_choice):  # noqa: ARG001
        from mail.core.tools import AgentToolCall

        completion = {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01ABC123",
                    "name": "pause_for_debug",
                    "input": {"note": "pausing"},
                }
            ],
        }
        call = AgentToolCall(
            tool_name="pause_for_debug",
            tool_args={"note": "pausing"},
            tool_call_id="toolu_01ABC123",
            completion=completion,
        )
        return None, [call]

    mail = MAILRuntime(
        agents={
            "supervisor": AgentCore(
                function=breakpoint_agent,
                comm_targets=["supervisor"],
                enable_entrypoint=True,
                enable_interswarm=False,
                can_complete_tasks=True,
            )
        },
        actions={},
        user_id="user-1",
        user_role="user",
        swarm_name="example",
        swarm_registry=None,
        enable_interswarm=False,
        entrypoint="supervisor",
        breakpoint_tools=["pause_for_debug"],
    )

    msg: MAILMessage = MAILMessage(
        id="m1",
        timestamp="2024-01-01T00:00:00Z",
        message=MAILRequest(
            task_id="t-break",
            request_id="r-break",
            sender=create_user_address("user-1"),
            recipient=create_agent_address("supervisor"),
            subject="Pause",
            body="hit breakpoint",
            sender_swarm=None,
            recipient_swarm=None,
            routing_info=None,
        ),
        msg_type="request",
    )

    loop_task = asyncio.create_task(mail.run_continuous())
    try:
        await asyncio.sleep(0)

        result = await asyncio.wait_for(
            mail.submit_and_wait(msg, timeout=2.0), timeout=3.0
        )
    finally:
        await mail.shutdown()
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    assert result["msg_type"] == "broadcast_complete"
    assert result["message"]["subject"] == "::breakpoint_tool_call::"

    payload = json.loads(result["message"]["body"])
    assert payload[0]["type"] == "function_call"
    assert payload[0]["name"] == "pause_for_debug"
    assert payload[0]["call_id"] == "toolu_01ABC123"
    assert payload[0]["id"] == "fc_toolu_01ABC123"
    assert payload[0]["status"] == "completed"
    assert json.loads(payload[0]["arguments"]) == {"note": "pausing"}
