# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import asyncio
import copy
import datetime
import json
import tempfile
import uuid
from types import MethodType
from typing import Any

import pytest

from mail.core.agents import AgentCore
from mail.core.message import (
    MAILBroadcast,
    MAILInterrupt,
    MAILInterswarmMessage,
    MAILMessage,
    MAILRequest,
    create_agent_address,
    create_user_address,
    format_agent_address,
)
from mail.core.runtime import AGENT_HISTORY_KEY, MAILRuntime
from mail.core.tools import AgentToolCall
from mail.net.registry import SwarmRegistry


def _create_agent_core(
    comm_targets: list[str],
    call_log: dict[str, bool] | None = None,
    *,
    log_key: str = "called",
) -> AgentCore:
    async def _agent(history: list[dict[str, Any]], tool_choice: str | dict[str, str]):  # noqa: ARG001
        if call_log is not None:
            call_log[log_key] = True
        return None, [
            AgentToolCall(
                tool_name="task_complete",
                tool_args={"finish_message": "done"},
                tool_call_id=str(uuid.uuid4()),
                completion={"role": "assistant", "content": "done"},
            )
        ]

    return AgentCore(function=_agent, comm_targets=comm_targets)


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
            sender=create_agent_address("tester"),
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
async def test_submit_prioritizes_message_types() -> None:
    """
    Within MAIL, messages should be assigned the following priority tiers:

    1. System message of any type
    2. User message of any type
    3. Agent interrupt, broadcast_complete
    4. Agent broadcast
    5. Agent request, response

    Within each category, messages are processed in FIFO order using a monotonically increasing sequence number to avoid dict comparisons.
    This test ensures that the runtime correctly prioritizes messages based on their type.
    """
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-1",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
    )

    await runtime.submit(_make_request("task-req"))
    await runtime.submit(_make_broadcast("task-bc"))
    await runtime.submit(_make_interrupt("task-int"))
    # broadcast_complete message uses broadcast structure with special type
    completion = _make_broadcast("task-comp", subject="Task complete")
    completion["msg_type"] = "broadcast_complete"
    await runtime.submit(completion)

    ordered_types = []
    for _ in range(4):
        priority, seq, message = await runtime.message_queue.get()
        runtime.message_queue.task_done()
        ordered_types.append((priority, seq, message["msg_type"]))

    msg_types = [m for (_, _, m) in ordered_types]
    assert (
        msg_types == ["interrupt", "broadcast_complete", "broadcast", "request"]
    ) or (msg_types == ["broadcast_complete", "interrupt", "broadcast", "request"])
    # Ensure FIFO ordering for equal priority (interrupt before completion because it was submitted first)
    assert ordered_types[0][0] == ordered_types[1][0] == 3
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
        user_role="user",
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

    await runtime._ensure_task_exists(task_id)
    runtime._submit_event("task_update", task_id, "intermediate status")

    update_event = await agen.__anext__()
    assert update_event.event == "task_update"
    assert update_event.data is not None
    update_payload = (
        json.loads(update_event.data)
        if isinstance(update_event.data, str)
        else update_event.data
    )
    assert update_payload["task_id"] == task_id
    assert update_payload["description"] == "intermediate status"

    completion_message = runtime._agent_task_complete(
        task_id=task_id,
        caller="supervisor",
        finish_message="All good",
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
async def test_agent_cannot_target_unlisted_local_recipient() -> None:
    """
    Local agents must not deliver messages to recipients outside their comm_targets.
    """
    helper_log = {"called": False}
    runtime = MAILRuntime(
        agents={
            "supervisor": _create_agent_core(comm_targets=[]),
            "helper": _create_agent_core(comm_targets=[], call_log=helper_log),
        },
        actions={},
        user_id="user-3",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
    )

    task_id = "task-disallowed-local"
    message = _make_request(task_id, sender="supervisor", recipient="helper")
    await runtime.submit(message)
    _, _, queued_message = await runtime.message_queue.get()
    await runtime._process_message(queued_message, None)

    # Helper should never receive the message
    assert helper_log["called"] is False

    # The runtime should queue a system response explaining the failure
    _, _, response_message = await runtime.message_queue.get()
    assert response_message["message"]["recipient"]["address"] == "supervisor"  # type: ignore
    assert response_message["message"]["subject"] == "::invalid_recipient::"
    assert "helper" in response_message["message"]["body"]
    runtime.message_queue.task_done()

    assert runtime.message_queue.empty()


@pytest.mark.asyncio
async def test_agent_cannot_target_unlisted_remote_recipient() -> None:
    """
    Agents should not route interswarm messages to recipients outside comm_targets.
    """

    class DummyRouter:
        def __init__(self) -> None:
            self.called = False

        async def route_message(self, *args, **kwargs):  # noqa: ANN001
            self.called = True
            raise AssertionError(
                "route_message should not be invoked for disallowed targets"
            )

    runtime = MAILRuntime(
        agents={
            "supervisor": _create_agent_core(comm_targets=["analyst"]),
        },
        actions={},
        user_id="user-4",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
        enable_interswarm=True,
    )
    runtime.interswarm_router = DummyRouter()  # type: ignore

    task_id = "task-disallowed-remote"
    remote_target = "remote-helper@swarm-beta"
    message = _make_request(task_id, sender="supervisor", recipient=remote_target)
    message["message"]["recipient_swarm"] = "swarm-beta"  # type: ignore
    await runtime.submit(message)
    _, _, queued_message = await runtime.message_queue.get()
    await runtime._process_message(queued_message, None)

    # Router must not be invoked
    assert runtime.interswarm_router.called is False  # type: ignore

    # System response should be queued with failure details
    _, _, response_message = await runtime.message_queue.get()
    assert response_message["message"]["recipient"]["address"] == "supervisor"  # type: ignore
    assert response_message["message"]["subject"] == "::invalid_recipient::"
    assert remote_target in response_message["message"]["body"]
    runtime.message_queue.task_done()

    assert runtime.message_queue.empty()


@pytest.mark.asyncio
async def test_agent_can_await_message_records_event() -> None:
    """
    Agents using `await_message` should emit an event and record tool history.
    """

    wait_reason = "waiting for coordinator"

    async def waiting_agent(
        history: list[dict[str, str]], task: str | dict[str, str]
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
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
    )

    task_id = "task-await"
    message = _make_request(task_id, sender="supervisor", recipient="analyst")

    await runtime.submit(message)
    await runtime.submit(_make_broadcast(task_id))
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

    # clean up broadcast queued for backlog
    while not runtime.message_queue.empty():
        runtime.message_queue.get_nowait()
        runtime.message_queue.task_done()


class _SpyRouter:
    def __init__(self) -> None:
        self.convert_calls: list[tuple[MAILMessage, str, list[str]]] = []
        self.forward_sent: list[MAILInterswarmMessage] = []
        self.back_sent: list[MAILInterswarmMessage] = []

    def convert_local_message_to_interswarm(
        self,
        message: MAILMessage,
        task_owner: str,
        task_contributors: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> MAILInterswarmMessage:
        self.convert_calls.append(
            (copy.deepcopy(message), task_owner, list(task_contributors))
        )
        recipient_swarms = message.get("recipient_swarms")
        assert isinstance(recipient_swarms, list) and recipient_swarms
        target_swarm = recipient_swarms[0]
        payload = copy.deepcopy(message["message"])
        return MAILInterswarmMessage(
            message_id=str(uuid.uuid4()),
            source_swarm="swarm-alpha",
            target_swarm=target_swarm,
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            payload=payload,
            msg_type=message["msg_type"],  # type: ignore
            auth_token="token-remote",
            task_owner=task_owner,
            task_contributors=list(task_contributors),
            metadata=metadata or {},
        )

    async def send_interswarm_message_forward(
        self, message: MAILInterswarmMessage
    ) -> None:
        self.forward_sent.append(message)

    async def send_interswarm_message_back(
        self, message: MAILInterswarmMessage
    ) -> None:
        self.back_sent.append(message)


@pytest.mark.asyncio
async def test_send_interswarm_message_forward_delegates_to_router() -> None:
    """
    Test that the runtime delegates to the interswarm router when sending an interswarm message to a remote swarm.
    """
    runtime = MAILRuntime(
        agents={"analyst": _create_agent_core(comm_targets=[])},
        actions={},
        user_id="user-remote",
        user_role="user",
        swarm_name="swarm-alpha",
        entrypoint="supervisor",
        enable_interswarm=True,
    )

    router = _SpyRouter()
    runtime.interswarm_router = router  # type: ignore[assignment]

    task_id = "task-remote"
    await runtime._ensure_task_exists(task_id)

    outbound = _make_request(
        task_id,
        sender="supervisor",
        recipient="analyst@swarm-beta",
    )
    outbound["recipient_swarms"] = ["swarm-beta"]  # type: ignore

    await runtime._send_interswarm_message(outbound)

    assert router.convert_calls, (
        "expected convert_local_message_to_interswarm to be called"
    )
    (converted_message, owner, contributors) = router.convert_calls[0]
    assert converted_message["message"]["task_id"] == task_id
    assert owner == runtime.mail_tasks[task_id].task_owner
    assert contributors == runtime.mail_tasks[task_id].task_contributors
    assert router.forward_sent, "expected forward send call"
    assert router.forward_sent[0]["target_swarm"] == "swarm-beta"


@pytest.mark.asyncio
async def test_send_interswarm_message_back_delegates_to_router() -> None:
    """
    Test that the runtime delegates to the interswarm router when replying to a remote swarm.
    """
    runtime = MAILRuntime(
        agents={"analyst": _create_agent_core(comm_targets=[])},
        actions={},
        user_id="user-remote",
        user_role="user",
        swarm_name="swarm-alpha",
        entrypoint="supervisor",
        enable_interswarm=True,
    )

    router = _SpyRouter()
    runtime.interswarm_router = router  # type: ignore[assignment]

    task_id = "task-remote"
    await runtime._ensure_task_exists(task_id)
    task_state = runtime.mail_tasks[task_id]
    task_state.task_contributors.append("agent:remote@swarm-beta")

    response = MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message={
            "task_id": task_id,
            "request_id": str(uuid.uuid4()),
            "sender": create_agent_address("supervisor"),
            "recipient": format_agent_address("supervisor", "swarm-beta"),
            "subject": "::task_complete::",
            "body": "Done",
            "sender_swarm": "swarm-alpha",
            "recipient_swarm": "swarm-beta",
            "routing_info": {},
        },
        msg_type="response",
    )
    response["recipient_swarms"] = ["swarm-beta"]  # type: ignore

    await runtime._send_interswarm_message(response)

    assert router.convert_calls, (
        "expected convert_local_message_to_interswarm to be called"
    )
    assert not router.forward_sent
    assert router.back_sent
    assert router.back_sent[0]["target_swarm"] == "swarm-beta"


@pytest.mark.asyncio
async def test_task_complete_idempotent_stashes_queue() -> None:
    """
    When a task is completed, the runtime should stash the message queue and mark the task as complete.
    """
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-complete",
        user_role="user",
        swarm_name="swarm-alpha",
        entrypoint="supervisor",
    )

    task_id = "task-complete"
    await runtime._ensure_task_exists(task_id)

    follow_up = _make_broadcast(task_id, subject="Follow-up")
    await runtime.submit(follow_up)
    assert runtime.message_queue.qsize() == 1

    call = AgentToolCall(
        tool_name="task_complete",
        tool_args={"finish_message": "done"},
        tool_call_id="call-1",
        completion={"role": "assistant", "content": "done"},
    )

    await runtime._handle_task_complete_call(task_id, "supervisor", call)

    task_state = runtime.mail_tasks[task_id]
    assert task_state.completed is True
    assert task_state.task_message_queue, "expected queued messages to be stashed"

    priority, seq, queued_message = await runtime.message_queue.get()
    assert queued_message["msg_type"] == "broadcast_complete"
    runtime.message_queue.task_done()
    assert runtime.message_queue.empty()

    duplicate_call = AgentToolCall(
        tool_name="task_complete",
        tool_args={"finish_message": "done"},
        tool_call_id="call-2",
        completion={"role": "assistant", "content": "done"},
    )

    await runtime._handle_task_complete_call(task_id, "supervisor", duplicate_call)

    assert runtime.message_queue.empty()
    history_key = AGENT_HISTORY_KEY.format(task_id=task_id, agent_name="supervisor")
    assert history_key in runtime.agent_histories
    assert (
        runtime.agent_histories[history_key][-1]["content"]
        == "SUCCESS: task already completed"
    )

    events = runtime.get_events_by_task_id(task_id)
    assert any(ev.event == "task_complete_call" for ev in events)
    assert any(ev.event == "task_complete_call_duplicate" for ev in events)


@pytest.mark.asyncio
async def test_task_complete_resolves_pending_future() -> None:
    """
    When a task is completed, the runtime should resolve the pending future.
    """
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-pending",
        user_role="user",
        swarm_name="pending-swarm",
        entrypoint="supervisor",
    )

    task_id = "task-future"
    await runtime._ensure_task_exists(task_id)

    pending: asyncio.Future[MAILMessage] = asyncio.Future()
    runtime.pending_requests[task_id] = pending

    call = AgentToolCall(
        tool_name="task_complete",
        tool_args={"finish_message": "great success"},
        tool_call_id="call-pending",
        completion={"role": "assistant", "content": "done"},
    )

    await runtime._handle_task_complete_call(task_id, "supervisor", call)

    assert pending.done(), "expected pending future to resolve immediately"
    result = pending.result()
    assert result["msg_type"] == "broadcast_complete"
    assert result["message"]["body"] == "great success"
    assert runtime.response_messages[task_id]["message"]["body"] == "great success"

    events = runtime.get_events_by_task_id(task_id)
    assert events, "expected streaming events to be emitted"
    final_event = events[-1]
    assert final_event.event == "new_message"
    assert isinstance(final_event.data, dict)
    extra = final_event.data.get("extra_data", {})
    assert (
        extra
        and extra.get("full_message", {}).get("message", {}).get("body")
        == "great success"
    )


@pytest.mark.asyncio
async def test_interswarm_message_preserves_user_pending_future() -> None:
    """
    When a user sends an interswarm message, the runtime should preserve the pending future.
    """
    runtime = MAILRuntime(
        agents={"supervisor": _create_agent_core(comm_targets=[])},
        actions={},
        user_id="user-pend",
        user_role="user",
        swarm_name="alpha",
        entrypoint="supervisor",
    )

    task_id = "task-user"
    await runtime._ensure_task_exists(task_id)
    pending: asyncio.Future[MAILMessage] = asyncio.Future()
    runtime.pending_requests[task_id] = pending

    interswarm_message = MAILInterswarmMessage(
        message_id=str(uuid.uuid4()),
        source_swarm="swarm-beta",
        target_swarm="alpha",
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        payload=MAILRequest(
            task_id=task_id,
            request_id=str(uuid.uuid4()),
            sender=format_agent_address("remote-agent", "swarm-beta"),
            recipient=format_agent_address("supervisor", "alpha"),
            subject="Hello",
            body="Body",
            sender_swarm="swarm-beta",
            recipient_swarm="alpha",
            routing_info={},
        ),
        msg_type="request",
        auth_token="token-remote",
        task_owner=runtime.this_owner,
        task_contributors=["agent:remote@swarm-beta", runtime.this_owner],
        metadata={},
    )

    await runtime._receive_interswarm_message(interswarm_message)

    assert runtime.pending_requests[task_id] is pending
    priority, seq, queued_message = await runtime.message_queue.get()
    runtime.message_queue.task_done()

    assert queued_message["message"]["task_id"] == task_id


@pytest.mark.asyncio
async def test_task_complete_notifies_remote_swarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-remote-complete",
        user_role="user",
        swarm_name="alpha",
        entrypoint="supervisor",
        enable_interswarm=True,
    )

    notified: dict[str, tuple[str, str, str] | None] = {"args": None}

    async def fake_notify(
        self: MAILRuntime, task: str, finish: str, caller: str
    ) -> None:
        notified["args"] = (task, finish, caller)

    monkeypatch.setattr(MAILRuntime, "_notify_remote_task_complete", fake_notify)

    task_id = "task-remote-complete"
    await runtime._ensure_task_exists(task_id)
    runtime.mail_tasks[task_id].add_remote_swarm("swarm-beta")

    call = AgentToolCall(
        tool_name="task_complete",
        tool_args={"finish_message": "All done"},
        tool_call_id="tc-remote",
        completion={"role": "assistant", "content": "done"},
    )

    await runtime._handle_task_complete_call(task_id, "supervisor", call)

    assert runtime.mail_tasks[task_id].remote_swarms == {"swarm-beta"}
    assert notified["args"] == (task_id, "All done", "supervisor")


@pytest.mark.asyncio
async def test_notify_remote_task_complete_sends_message() -> None:
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-notify",
        user_role="user",
        swarm_name="alpha",
        entrypoint="supervisor",
        enable_interswarm=True,
    )
    sent: list[MAILMessage] = []
    runtime.interswarm_router = object()  # type: ignore[assignment]

    async def fake_send(self: MAILRuntime, message: MAILMessage) -> None:
        sent.append(message)

    runtime._send_interswarm_message = MethodType(fake_send, runtime)  # type: ignore[assignment]

    task_id = "task-notify"
    await runtime._ensure_task_exists(task_id)
    runtime.mail_tasks[task_id].add_remote_swarm("swarm-beta")

    await runtime._notify_remote_task_complete(task_id, "Done", "supervisor")

    assert sent, "expected interswarm completion message"
    outbound = sent[0]
    assert outbound["message"]["task_id"] == task_id
    assert outbound["msg_type"] == "response"
    assert outbound["message"]["subject"] == "::task_complete::"


@pytest.mark.asyncio
async def test_await_message_errors_when_queue_empty() -> None:
    """
    Awaiting with an empty queue should surface a tool error and notify the agent.
    """

    async def waiting_agent(
        history: list[dict[str, Any]], task: str | dict[str, str]
    ) -> tuple[str | None, list[AgentToolCall]]:
        call = AgentToolCall(
            tool_name="await_message",
            tool_args={},
            tool_call_id="await-empty",
            completion={"role": "assistant", "content": "waiting"},
        )
        return None, [call]

    runtime = MAILRuntime(
        agents={"analyst": AgentCore(function=waiting_agent, comm_targets=[])},
        actions={},
        user_id="user-await",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
    )

    task_id = "task-await-empty"
    message = _make_request(task_id, sender="supervisor", recipient="analyst")

    await runtime.submit(message)
    _priority, _seq, queued_message = await runtime.message_queue.get()
    await runtime._process_message(queued_message)

    while runtime.active_tasks:
        await asyncio.gather(*list(runtime.active_tasks))

    history_key = AGENT_HISTORY_KEY.format(task_id=task_id, agent_name="analyst")
    history = runtime.agent_histories[history_key]
    assert history[-1]["role"] == "tool"
    assert "message queue is empty" in history[-1]["content"]

    events = runtime.get_events_by_task_id(task_id)
    error_events = [event for event in events if event.event == "agent_error"]
    assert error_events, "expected agent_error event when queue is empty"
    assert "message queue is empty" in error_events[-1].data["description"]  # type: ignore[index]

    (
        response_priority,
        response_seq,
        response_message,
    ) = await runtime.message_queue.get()
    assert response_message["msg_type"] == "response"
    assert response_message["message"]["subject"] == "::tool_call_error::"
    assert "message queue is empty" in response_message["message"]["body"]
    runtime.message_queue.task_done()


@pytest.mark.asyncio
async def test_help_tool_emits_broadcast_and_event() -> None:
    """
    Help tool calls should queue a help broadcast and emit a tracking event.
    """

    async def helper_agent(
        history: list[dict[str, Any]], tool_choice: str | dict[str, str]
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
        user_role="user",
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
    assert help_message["message"]["recipients"] == [  # type: ignore
        create_agent_address("analyst")
    ]
    runtime.message_queue.task_done()

    events = runtime.get_events_by_task_id(task_id)
    help_events = [event for event in events if event.event == "help_called"]
    assert help_events, "expected help_called event to be emitted"
    event_data = help_events[-1].data
    assert isinstance(event_data, dict)
    assert event_data["description"].endswith("called help")

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
        user_role="user",
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


@pytest.mark.asyncio
async def test_submit_event_tracks_events_by_task() -> None:
    """
    Events should be stored and filtered per task id.
    """
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-4",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
    )

    await runtime._ensure_task_exists("task-a")
    await runtime._ensure_task_exists("task-b")

    runtime._submit_event("update", "task-a", "first")
    runtime._submit_event("update", "task-b", "second")

    assert runtime._events_available_by_task["task-a"].is_set()
    assert runtime._events_available_by_task["task-b"].is_set()

    events_a = runtime.get_events_by_task_id("task-a")
    assert len(events_a) == 1
    assert events_a[0].event == "update"
    assert events_a[0].data is not None
    assert events_a[0].data["description"] == "first"

    events_missing = runtime.get_events_by_task_id("missing")
    assert events_missing == []


@pytest.mark.asyncio
async def test_run_continuous_max_steps_is_per_task() -> None:
    """
    max_steps should be tracked per task, not globally.
    """
    runtime = MAILRuntime(
        agents={"supervisor": _create_agent_core(comm_targets=[])},
        actions={},
        user_id="user-steps",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
    )

    def _send_message(task_id: str) -> MAILMessage:
        return MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILRequest(
                task_id=task_id,
                request_id=str(uuid.uuid4()),
                sender=create_user_address("user-steps"),
                recipient=create_agent_address("supervisor"),
                subject="Test",
                body="Body",
                sender_swarm=None,
                recipient_swarm=None,
                routing_info={},
            ),
            msg_type="request",
        )

    runner = asyncio.create_task(runtime.run_continuous(max_steps=1))
    try:
        task_a = "task-a"
        await runtime.submit_and_wait(_send_message(task_a))

        task_b = "task-b"
        await runtime.submit_and_wait(_send_message(task_b))

        events_b = runtime.get_events_by_task_id(task_b)
        assert not any(event.data is None for event in events_b)
        assert not any(
            "::maximum_steps_reached::" in event.data["description"] # type: ignore
            for event in events_b
        )
    finally:
        await runtime.shutdown()
        await runner


@pytest.mark.asyncio
async def test_run_task_breakpoint_resume_requires_task_id() -> None:
    runtime = MAILRuntime(
        agents={},
        actions={},
        user_id="user-5",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
    )

    response = await runtime.run_task(resume_from="breakpoint_tool_call")

    assert response["msg_type"] == "broadcast_complete"
    assert response["message"]["subject"] == "::runtime_error::"
    assert "parameter 'task_id' is required" in response["message"]["body"]


@pytest.mark.asyncio
async def test_run_task_breakpoint_resume_updates_history_and_resumes() -> None:
    task_id = "task-breakpoint"
    tool_caller = "analyst"

    async def noop_agent(
        history: list[dict[str, str]], task: str | dict[str, str]
    ) -> tuple[str | None, list]:
        return ("ack", [])

    runtime = MAILRuntime(
        agents={tool_caller: AgentCore(function=noop_agent, comm_targets=[])},
        actions={},
        user_id="user-6",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
    )
    await runtime._ensure_task_exists(task_id)

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

    runtime.last_breakpoint_caller = {task_id: tool_caller}
    runtime.last_breakpoint_tool_calls = {
        task_id: [
            AgentToolCall(
                tool_name="noop",
                tool_args={},
                tool_call_id="noop-1",
                completion={"role": "assistant", "content": "done"},
            )
        ]
    }

    result = await runtime.run_task(
        task_id=task_id,
        resume_from="breakpoint_tool_call",
        breakpoint_tool_call_result='{"content": "done"}',
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
        history: list[dict[str, str]], task: str | dict[str, str]
    ) -> tuple[str | None, list]:
        return ("ack", [])

    runtime = MAILRuntime(
        agents={tool_caller: AgentCore(function=noop_agent, comm_targets=[])},
        actions={},
        user_id="user-7",
        user_role="user",
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
    assert response["message"]["subject"] == "::task_error::"
    assert "task 'missing-task' not found" in response["message"]["body"]
    assert task_id not in runtime.pending_requests


@pytest.mark.asyncio
async def test_submit_and_wait_breakpoint_resume_updates_history_and_resolves() -> None:
    task_id = "task-continuous"
    tool_caller = "analyst"

    async def noop_agent(
        history: list[dict[str, str]], task: str | dict[str, str]
    ) -> tuple[str | None, list]:
        return ("ack", [])

    runtime = MAILRuntime(
        agents={tool_caller: AgentCore(function=noop_agent, comm_targets=[])},
        actions={},
        user_id="user-8",
        user_role="user",
        swarm_name="example",
        entrypoint="supervisor",
    )
    await runtime._ensure_task_exists(task_id)

    # Set up breakpoint state required for resume_from="breakpoint_tool_call"
    mock_tool_call = AgentToolCall(
        tool_name="breakpoint_action",
        tool_args={},
        tool_call_id="bp-call-1",
        completion={"role": "assistant", "content": "breakpoint"},
    )
    runtime.last_breakpoint_tool_calls[task_id] = [mock_tool_call]
    runtime.last_breakpoint_caller[task_id] = tool_caller

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
    history: list[dict[str, object]], tool_choice: str | dict[str, str]
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
        user_role="user",
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
            user_role="user",
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
