# SPDX-License-Identifier: Apache-2.0

import asyncio
import datetime
import uuid

import pytest

from mail.core.message import (
    MAILBroadcast,
    MAILInterrupt,
    MAILMessage,
    MAILRequest,
    create_agent_address,
    create_user_address,
)
from mail.core.runtime import MAILRuntime


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
