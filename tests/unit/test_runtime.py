# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import asyncio
import datetime
import tempfile
import uuid
from types import MethodType
from typing import Any

import pytest

from mail.core.agents import AgentCore
from mail.core.message import (
    MAILBroadcast,
    MAILInterrupt,
    MAILMessage,
    MAILRequest,
    create_agent_address,
    create_user_address,
)
from mail.core.runtime import AGENT_HISTORY_KEY, MAILRuntime
from mail.core.tools import AgentToolCall
from mail.net.registry import SwarmRegistry


def _make_request(
    task_id: str, sender: str = "supervisor", recipient: str = "analyst"
) -> MAILMessage:
    """
    Build a minimal MAIL request message for testing.
    """
    return MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message=MAILRequest(
            task_id=task_id,
            request_id=str(uuid.uuid4()),
            sender=create_agent_address(sender),
            recipient=create_agent_address(recipient),
            subject="Test",
            body="Body",
            sender_swarm=None,
            recipient_swarm=None,
            routing_info={},
        ),
        msg_type="request",
    )


def _make_broadcast(task_id: str, subject: str = "Update") -> MAILMessage:
    return MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message=MAILBroadcast(
            task_id=task_id,
            broadcast_id=str(uuid.uuid4()),
            sender=create_user_address("tester"),
            recipients=[create_agent_address("analyst")],
            subject=subject,
            body="Broadcast body",
            sender_swarm=None,
            recipient_swarms=None,
            routing_info={},
        ),
        msg_type="broadcast",
    )


def _make_interrupt(task_id: str) -> MAILMessage:
    return MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message=MAILInterrupt(
            task_id=task_id,
            interrupt_id=str(uuid.uuid4()),
            sender=create_agent_address("supervisor"),
            recipients=[create_agent_address("analyst")],
            subject="Interrupt",
            body="Stop",
            sender_swarm=None,
            recipient_swarms=None,
            routing_info={},
        ),
        msg_type="interrupt",
    )


@pytest.mark.asyncio
async def test_submit_prioritises_message_types() -> None:
    """
    Interrupts and completions should outrank broadcasts, which outrank requests.
    """
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-1",
        swarm_name="example",
        entrypoint="supervisor",
    )

    await runtime.submit(_make_request("task-req"))
    await runtime.submit(_make_broadcast("task-bc"))
    await runtime.submit(_make_interrupt("task-int"))
    # broadcast_complete message reuse broadcast structure with special type
    completion = _make_broadcast("task-comp", subject="Task complete")
    completion["msg_type"] = "broadcast_complete"
    await runtime.submit(completion)

    ordered_types = []
    for _ in range(4):
        priority, seq, message = await runtime.message_queue.get()
        runtime.message_queue.task_done()
        ordered_types.append((priority, seq, message["msg_type"]))

    msg_types = [m for (_, _, m) in ordered_types]
    assert msg_types == ["interrupt", "broadcast_complete", "broadcast", "request"]
    # Ensure FIFO ordering for equal priority (interrupt before completion because it was submitted first)
    assert ordered_types[0][0] == ordered_types[1][0] == 1
    assert ordered_types[0][1] < ordered_types[1][1]


@pytest.mark.asyncio
async def test_submit_and_stream_handles_timeout_and_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Streaming should emit heartbeats, relay task events, and finish with `task_complete`.
    """
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-2",
        swarm_name="example",
        entrypoint="supervisor",
    )
    task_id = "task-stream"
    message = _make_request(task_id)

    original_wait_for = asyncio.wait_for
    call_count = {"count": 0}

    async def fake_wait_for(awaitable, timeout):  # noqa: ANN001
        call_count["count"] += 1
        if call_count["count"] == 1:
            return await original_wait_for(awaitable, 0)
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    stream = runtime.submit_and_stream(message)
    agen = stream.__aiter__()

    ping_event = await agen.__anext__()
    assert ping_event.event == "ping"

    runtime._ensure_task_exists(task_id)
    runtime._submit_event("task_update", task_id, "intermediate status")

    update_event = await agen.__anext__()
    assert update_event.event == "task_update"
    assert update_event.data is not None
    assert update_event.data["task_id"] == task_id
    assert update_event.data["description"] == "intermediate status"

    completion_message = runtime._system_broadcast(
        task_id=task_id,
        subject="Done",
        body="All good",
        task_complete=True,
    )
    future = runtime.pending_requests[task_id]
    future.set_result(completion_message)

    final_event = await agen.__anext__()
    assert final_event.event == "task_complete"
    assert final_event.data is not None
    assert final_event.data["response"] == "All good"

    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()

    runtime.pending_requests.pop(task_id, None)
    # Drain any queued messages created during the test
    while not runtime.message_queue.empty():
        runtime.message_queue.get_nowait()
        runtime.message_queue.task_done()

    await stream.aclose()


@pytest.mark.asyncio
async def test_agent_can_await_message_records_event() -> None:
    """
    Agents using `await_message` should emit an event and record tool history.
    """

    wait_reason = "waiting for coordinator"

    async def waiting_agent(
        history: list[dict[str, str]], task: str
    ) -> tuple[str | None, list[AgentToolCall]]:
        call = AgentToolCall(
            tool_name="await_message",
            tool_args={"reason": wait_reason},
            tool_call_id="await-1",
            completion={
                "role": "assistant",
                "content": "I'll wait for the next message.",
            },
        )
        return (None, [call])

    runtime = MAILRuntime(
        agents={"analyst": AgentCore(function=waiting_agent, comm_targets=[])},
        actions={},
        user_id="user-await",
        swarm_name="example",
        entrypoint="supervisor",
    )

    task_id = "task-await"
    message = _make_request(task_id, sender="supervisor", recipient="analyst")

    await runtime.submit(message)
    _priority, _seq, queued_message = await runtime.message_queue.get()
    await runtime._process_message(queued_message)

    while runtime.active_tasks:
        await asyncio.gather(*list(runtime.active_tasks))

    history_key = AGENT_HISTORY_KEY.format(task_id=task_id, agent_name="analyst")
    history = runtime.agent_histories[history_key]
    assert history[-1]["role"] == "tool"
    assert "waiting for a new message" in history[-1]["content"]

    events = runtime.get_events_by_task_id(task_id)
    await_events = [event for event in events if event.event == "await_message"]
    assert await_events, "expected await_message event to be emitted"
    await_event = await_events[-1]
    assert await_event.data is not None
    assert (
        await_event.data["description"]
        == f"agent 'analyst' is awaiting a new message: {wait_reason}"
    )
    assert await_event.data["extra_data"]["reason"] == wait_reason


@pytest.mark.asyncio
async def test_help_tool_emits_broadcast_and_event() -> None:
    """
    Help tool calls should queue a help broadcast and emit a tracking event.
    """

    async def helper_agent(
        history: list[dict[str, Any]], tool_choice: str
    ) -> tuple[str | None, list[AgentToolCall]]:
        call = AgentToolCall(
            tool_name="help",
            tool_args={"get_summary": False, "get_identity": True},
            tool_call_id="help-1",
            completion={"role": "assistant", "content": "requesting help"},
        )
        return None, [call]

    runtime = MAILRuntime(
        agents={"analyst": AgentCore(function=helper_agent, comm_targets=[])},
        actions={},
        user_id="user-help",
        swarm_name="example",
        entrypoint="analyst",
    )

    task_id = "task-help"
    message = _make_request(task_id, sender="supervisor", recipient="analyst")

    await runtime.submit(message)
    _priority, _seq, queued_message = await runtime.message_queue.get()
    await runtime._process_message(queued_message)

    while runtime.active_tasks:
        await asyncio.gather(*list(runtime.active_tasks))

    _help_priority, _help_seq, help_message = await runtime.message_queue.get()
    assert help_message["msg_type"] == "broadcast"
    assert help_message["message"]["subject"] == "::help::"
    help_body = help_message["message"]["body"]
    assert "YOUR IDENTITY" in help_body
    assert "Name" in help_body and "example" in help_body
    assert help_message["message"]["recipients"] == [
        create_agent_address("analyst")
    ]
    runtime.message_queue.task_done()

    events = runtime.get_events_by_task_id(task_id)
    help_events = [event for event in events if event.event == "help_called"]
    assert help_events, "expected help_called event to be emitted"
    event_data = help_events[-1].data
    assert isinstance(event_data, dict)
    assert event_data["description"].endswith("called 'help'")

    while not runtime.message_queue.empty():
        runtime.message_queue.get_nowait()
        runtime.message_queue.task_done()


def test_system_broadcast_requires_recipients_for_non_completion() -> None:
    """
    Non-task-complete broadcasts must define recipients.
    """
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-3",
        swarm_name="example",
        entrypoint="supervisor",
    )

    with pytest.raises(ValueError):
        runtime._system_broadcast(
            task_id="task", subject="Alert", body="Missing recipients"
        )

    complete = runtime._system_broadcast(
        task_id="task",
        subject="Wrapped",
        body="Final",
        task_complete=True,
    )
    assert complete["msg_type"] == "broadcast_complete"
    recipients = complete["message"]["recipients"]  # type: ignore
    assert len(recipients) == 1 and recipients[0]["address"] == "all"


def test_submit_event_tracks_events_by_task() -> None:
    """
    Events should be stored and filtered per task id.
    """
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-4",
        swarm_name="example",
        entrypoint="supervisor",
    )

    runtime._ensure_task_exists("task-a")
    runtime._ensure_task_exists("task-b")

    runtime._submit_event("update", "task-a", "first")
    runtime._submit_event("update", "task-b", "second")

    assert runtime._events_available.is_set()

    events_a = runtime.get_events_by_task_id("task-a")
    assert len(events_a) == 1
    assert events_a[0].event == "update"
    assert events_a[0].data is not None
    assert events_a[0].data["description"] == "first"

    events_missing = runtime.get_events_by_task_id("missing")
    assert events_missing == []


@pytest.mark.asyncio
async def test_run_task_breakpoint_resume_requires_task_id() -> None:
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-5",
        swarm_name="example",
        entrypoint="supervisor",
    )

    response = await runtime.run_task(resume_from="breakpoint_tool_call")

    assert response["msg_type"] == "broadcast_complete"
    assert response["message"]["subject"] == "Runtime Error"
    assert "parameter 'task_id' is required" in response["message"]["body"]


@pytest.mark.asyncio
async def test_run_task_breakpoint_resume_updates_history_and_resumes() -> None:
    task_id = "task-breakpoint"
    tool_caller = "analyst"

    async def noop_agent(
        history: list[dict[str, str]], task: str
    ) -> tuple[str | None, list]:
        return ("ack", [])

    runtime = MAILRuntime(
        agents={tool_caller: AgentCore(function=noop_agent, comm_targets=[])},
        actions={},
        user_id="user-6",
        swarm_name="example",
        entrypoint="supervisor",
    )
    runtime._ensure_task_exists(task_id)

    action_override_called_with: dict[str, object] = {}
    expected_result = runtime._system_broadcast(
        task_id=task_id,
        subject="Resumed",
        body="complete",
        task_complete=True,
    )

    async def fake_run_loop(self: MAILRuntime, task: str, override) -> MAILMessage:
        action_override_called_with["task_id"] = task
        action_override_called_with["override"] = override
        return expected_result

    runtime._run_loop_for_task = MethodType(fake_run_loop, runtime)  # type: ignore

    async def action_override(payload: dict[str, object]) -> dict[str, object] | str:
        return payload

    result = await runtime.run_task(
        task_id=task_id,
        resume_from="breakpoint_tool_call",
        breakpoint_tool_caller=tool_caller,
        breakpoint_tool_call_result="done",
        action_override=action_override,
    )

    assert result == expected_result
    assert action_override_called_with["task_id"] == task_id
    assert action_override_called_with["override"] is action_override

    history_key = AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=tool_caller)
    assert runtime.agent_histories[history_key][-1]["role"] == "tool"
    assert runtime.agent_histories[history_key][-1]["content"] == "done"

    _priority, _seq, queued_message = runtime.message_queue.get_nowait()
    runtime.message_queue.task_done()
    assert queued_message["message"]["subject"] == "::action_complete_broadcast::"
    assert queued_message["msg_type"] == "broadcast"
    recipient = queued_message["message"]["recipients"][0]  # type: ignore
    assert recipient["address"] == create_agent_address(tool_caller)["address"]


@pytest.mark.asyncio
async def test_submit_and_wait_breakpoint_resume_requires_existing_task() -> None:
    task_id = "missing-task"
    tool_caller = "analyst"

    async def noop_agent(
        history: list[dict[str, str]], task: str
    ) -> tuple[str | None, list]:
        return ("ack", [])

    runtime = MAILRuntime(
        agents={tool_caller: AgentCore(function=noop_agent, comm_targets=[])},
        actions={},
        user_id="user-7",
        swarm_name="example",
        entrypoint="supervisor",
    )

    message = _make_request(task_id)

    response = await runtime.submit_and_wait(
        message,
        resume_from="breakpoint_tool_call",
        breakpoint_tool_caller=tool_caller,
        breakpoint_tool_call_result="ready",
    )

    assert response["msg_type"] == "broadcast_complete"
    assert response["message"]["subject"] == "Task Error"
    assert "task 'missing-task' not found" in response["message"]["body"]
    assert task_id not in runtime.pending_requests


@pytest.mark.asyncio
async def test_submit_and_wait_breakpoint_resume_updates_history_and_resolves() -> None:
    task_id = "task-continuous"
    tool_caller = "analyst"

    async def noop_agent(
        history: list[dict[str, str]], task: str
    ) -> tuple[str | None, list]:
        return ("ack", [])

    runtime = MAILRuntime(
        agents={tool_caller: AgentCore(function=noop_agent, comm_targets=[])},
        actions={},
        user_id="user-8",
        swarm_name="example",
        entrypoint="supervisor",
    )
    runtime._ensure_task_exists(task_id)

    completion_message = runtime._system_broadcast(
        task_id=task_id,
        subject="Done",
        body="complete",
        task_complete=True,
    )

    async def resolve_future() -> None:
        while task_id not in runtime.pending_requests:
            await asyncio.sleep(0)
        future = runtime.pending_requests.pop(task_id)
        future.set_result(completion_message)

    completer = asyncio.create_task(resolve_future())

    message = _make_request(task_id)
    result = await runtime.submit_and_wait(
        message,
        resume_from="breakpoint_tool_call",
        breakpoint_tool_caller=tool_caller,
        breakpoint_tool_call_result="ready",
    )

    await completer

    assert result == completion_message

    history_key = AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=tool_caller)
    assert runtime.agent_histories[history_key][-1]["role"] == "tool"
    assert runtime.agent_histories[history_key][-1]["content"] == "ready"

    _priority, _seq, resume_message = runtime.message_queue.get_nowait()
    runtime.message_queue.task_done()
    assert resume_message["message"]["subject"] == "::action_complete_broadcast::"
    recipient = resume_message["message"]["recipients"][0]  # type: ignore
    assert recipient["address"] == create_agent_address(tool_caller)["address"]

    assert task_id not in runtime.pending_requests


async def _noop_agent_fn(
    history: list[dict[str, object]], tool_choice: str
) -> tuple[str | None, list]:
    return None, []


def _make_runtime_agents() -> dict[str, AgentCore]:
    return {
        "supervisor": AgentCore(_noop_agent_fn, comm_targets=["analyst", "math"]),
        "analyst": AgentCore(_noop_agent_fn, comm_targets=["supervisor", "math"]),
        "math": AgentCore(_noop_agent_fn, comm_targets=["supervisor", "analyst"]),
    }


def _make_broadcast_all(task_id: str, sender: str = "supervisor") -> MAILMessage:
    return MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message=MAILBroadcast(
            task_id=task_id,
            broadcast_id=str(uuid.uuid4()),
            sender=create_agent_address(sender),
            recipients=[create_agent_address("all")],
            subject="Announcement",
            body="payload",
            sender_swarm=None,
            recipient_swarms=None,
            routing_info={},
        ),
        msg_type="broadcast",
    )


@pytest.mark.asyncio
async def test_broadcast_all_excludes_sender_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MAILRuntime(
        agents=_make_runtime_agents(),
        actions={},
        user_id="user-1",
        swarm_name="example",
        entrypoint="supervisor",
    )

    dispatched: list[str] = []

    def record_send(
        self: MAILRuntime, recipient: str, message: MAILMessage, _override=None
    ) -> None:  # type: ignore[override]
        dispatched.append(recipient)

    monkeypatch.setattr(runtime, "_send_message", MethodType(record_send, runtime))

    broadcast = _make_broadcast_all("task-broadcast")
    await runtime._process_message(broadcast)

    assert set(dispatched) == {"analyst", "math"}
    assert "supervisor" not in dispatched
    assert broadcast["message"]["recipients"] == [create_agent_address("all")]  # type: ignore


@pytest.mark.asyncio
async def test_broadcast_all_excludes_sender_with_interswarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = SwarmRegistry(
            "example", "http://example.test", persistence_file=f"{tmpdir}/registry.json"
        )
        runtime = MAILRuntime(
            agents=_make_runtime_agents(),
            actions={},
            user_id="user-1",
            swarm_name="example",
            entrypoint="supervisor",
            swarm_registry=registry,
            enable_interswarm=True,
        )

        dispatched: list[str] = []

        def record_send(
            self: MAILRuntime, recipient: str, message: MAILMessage, _override=None
        ) -> None:  # type: ignore[override]
            dispatched.append(recipient)

        monkeypatch.setattr(runtime, "_send_message", MethodType(record_send, runtime))

        broadcast = _make_broadcast_all("task-broadcast-remote")
        await runtime._process_message(broadcast)

        assert set(dispatched) == {"analyst", "math"}
        assert "supervisor" not in dispatched
        assert broadcast["message"]["recipients"] == [create_agent_address("all")]  # type: ignore
