# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import json
import uuid

import pytest

from mail.core.message import (
    MAILMessage,
    MAILRequest,
    create_agent_address,
    format_agent_address,
)
from mail.net.registry import SwarmRegistry
from mail.net.router import InterswarmRouter, StreamHandler


def make_request_to(agent: str) -> MAILMessage:
    """
    Make a formatted `MAILMessage` request to an agent.
    """
    return MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message=MAILRequest(
            task_id="t1",
            request_id="r1",
            sender=create_agent_address("supervisor"),
            recipient=create_agent_address(agent),
            subject="Hi",
            body="Body",
            sender_swarm="example",
            recipient_swarm="example",
            routing_info={},
        ),
        msg_type="request",
    )


@pytest.mark.asyncio
async def test_route_message_local(monkeypatch: pytest.MonkeyPatch):
    """
    Test that a message is routed to the local handler when the recipient is in the local swarm.
    """
    registry = SwarmRegistry("example", "http://localhost:8000")
    router = InterswarmRouter(registry, "example")

    received: list[MAILMessage] = []

    async def handler(msg: MAILMessage):
        received.append(msg)

    router.register_message_handler("local_message_handler", handler)

    msg = make_request_to("analyst")
    out = await router.route_message(msg)

    # Handler should have been called with a local-recipients message
    assert received, "local handler was not called"
    handled = received[0]
    assert "recipient" in handled["message"]
    assert handled["message"]["recipient"]["address"] == "analyst"  # type: ignore
    assert out["msg_type"] == "request"


@pytest.mark.asyncio
async def test_route_message_mixed_local_and_remote(monkeypatch: pytest.MonkeyPatch):
    """
    Test that a message is routed to the remote handler when the recipient is in a remote swarm.
    """
    registry = SwarmRegistry("example", "http://localhost:8000")
    # Register a remote swarm endpoint
    registry.register_swarm("remote", "http://remote:9999")

    router = InterswarmRouter(registry, "example")

    # Capture remote route argument
    captured: dict[str, MAILMessage | None] = {"msg": None}

    async def fake_remote(
        mm: MAILMessage,
        swarm: str,
        stream_requested: bool = False,
        stream_handler: StreamHandler | None = None,
        ignore_stream_pings: bool = False,
        is_response: bool = False,
    ):  # noqa: ANN001
        captured["msg"] = mm
        return mm

    monkeypatch.setattr(router, "_route_to_remote_swarm", fake_remote)

    # Needed to accept local messages
    async def handler(_):  # noqa: ANN001
        return None

    router.register_message_handler("local_message_handler", handler)

    # Build a broadcast to both local and remote agents
    msg = MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message={
            "task_id": "t1",
            "broadcast_id": "b1",
            "sender": create_agent_address("supervisor"),
            "recipients": [
                create_agent_address("analyst"),
                format_agent_address("helper", "remote"),
            ],
            "subject": "Broadcast",
            "body": "Test",
            "sender_swarm": "example",
            "recipient_swarms": ["example", "remote"],
            "routing_info": {},
        },
        msg_type="broadcast",
    )

    await router.route_message(msg)

    # Assert the remote message was created with correct addressing metadata
    assert captured["msg"] is not None
    remote_msg = captured["msg"]  # type: ignore[assignment]
    assert "recipients" in remote_msg["message"]
    addrs = [a["address"] for a in remote_msg["message"]["recipients"]]  # type: ignore
    assert addrs == ["helper@remote"]
    assert remote_msg["message"]["recipient_swarms"] == ["remote"]  # type: ignore
    assert remote_msg["message"]["sender_swarm"] == "example"


class _ChunkIterator:
    """
    Async iterator that yields predefined byte chunks.
    """

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = [chunk.encode("utf-8") for chunk in chunks]

    def __aiter__(self):  # noqa: D401
        return self

    async def __anext__(self) -> bytes:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _FakeResponse:
    """
    Minimal stand-in for `aiohttp.ClientResponse`.
    """

    def __init__(self, chunks: list[str]):
        self.headers = {"Content-Type": "text/event-stream"}
        self.content = _ChunkIterator(chunks)

    async def release(self) -> None:
        return None


class _SimpleResponse:
    """
    Minimal context manager for JSON responses.
    """

    def __init__(self, status: int, body: str, *, headers: dict[str, str] | None = None, reason: str = "") -> None:
        self.status = status
        self._body = body
        self.headers = headers or {"Content-Type": "application/json"}
        self.reason = reason

    async def __aenter__(self) -> "_SimpleResponse":
        return self

    async def __aexit__(self, exc_type, exc: BaseException | None, tb) -> bool:  # type: ignore[override]
        return False

    async def text(self) -> str:
        return self._body

    async def release(self) -> None:
        return None


class _CaptureSession:
    """
    Fake aiohttp session that records calls and returns predetermined responses.
    """

    def __init__(self, responses: list[_SimpleResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, json: object = None, headers: dict[str, str] | None = None, timeout: object = None):  # noqa: ANN001
        if not self._responses:
            raise AssertionError("no responses left to return")
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_consume_stream_returns_final_message(monkeypatch: pytest.MonkeyPatch):
    """
    Ensure `_consume_stream` parses SSE events and returns the final message.
    """
    registry = SwarmRegistry("example", "http://localhost:8000")
    router = InterswarmRouter(registry, "example")

    original = make_request_to("helper@remote")
    task_id = original["message"]["task_id"]

    message_payload = {
        "task_id": task_id,
        "extra_data": {"full_message": original},
    }
    complete_payload = {"task_id": task_id, "response": "done"}

    chunks = [
        "event:new_message\n",
        f"data:{json.dumps(message_payload)}\n",
        "\n",
        "event:task_complete\n",
        f"data:{json.dumps(complete_payload)}\n",
        "\n",
    ]

    fake_response = _FakeResponse(chunks)

    received_events: list[tuple[str, str | None]] = []

    async def handler(event: str, data: str | None) -> None:
        received_events.append((event, data))

    result = await router._consume_stream(
        fake_response,  # type: ignore[arg-type]
        original,
        "remote",
        stream_handler=handler,
    )

    assert result["message"]["task_id"] == task_id
    assert any(evt == "new_message" for evt, _ in received_events)
    assert any(evt == "task_complete" for evt, _ in received_events)


@pytest.mark.asyncio
async def test_iter_sse_ignores_ping(monkeypatch: pytest.MonkeyPatch):
    """
    Verify that ping frames can be ignored when requested.
    """
    registry = SwarmRegistry("example", "http://localhost:8000")
    router = InterswarmRouter(registry, "example")

    original = make_request_to("helper@remote")
    task_id = original["message"]["task_id"]

    chunks = [
        "event:ping\n",
        "data:{}\n",
        "\n",
        "event:task_complete\n",
        f"data:{json.dumps({'task_id': task_id, 'response': 'ok'})}\n",
        "\n",
    ]

    fake_response = _FakeResponse(chunks)

    captured: list[str] = []

    async def handler(event: str, data: str | None) -> None:
        captured.append(event)

    await router._consume_stream(
        fake_response,  # type: ignore[arg-type]
        original,
        "remote",
        stream_handler=handler,
        ignore_stream_pings=True,
    )

    assert captured == ["task_complete"]


@pytest.mark.asyncio
async def test_route_response_uses_response_endpoint() -> None:
    """
    Ensure responses are delivered via `/interswarm/response` without wrapping.
    """
    registry = SwarmRegistry("example", "http://localhost:8000")
    registry.register_swarm("remote", "http://remote:9999", auth_token="token-remote")
    router = InterswarmRouter(registry, "example")
    router.session = _CaptureSession(
        [
            _SimpleResponse(
                200,
                json.dumps({"status": "response_processed", "task_id": "task-1"}),
            )
        ]
    )

    message = MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message={
            "task_id": "task-1",
            "request_id": "req-1",
            "sender": create_agent_address("supervisor"),
            "recipient": format_agent_address("supervisor", "remote"),
            "subject": "::task_complete::",
            "body": "Done",
            "sender_swarm": "example",
            "recipient_swarm": "remote",
            "routing_info": {},
        },
        msg_type="response",
    )

    result = await router._route_to_remote_swarm(
        message,
        "remote",
        is_response=True,
    )

    assert router.session.calls, "expected HTTP call"
    call = router.session.calls[0]
    assert str(call["url"]).endswith("/interswarm/response")
    payload = call["json"]
    assert isinstance(payload, dict)
    assert payload["msg_type"] == "response"
    assert payload["message"]["sender_swarm"] == "example"
    assert payload["message"]["recipient_swarm"] == "remote"
    assert result["msg_type"] == "response"
    assert result["message"]["subject"] == "::task_complete::"


@pytest.mark.asyncio
async def test_route_response_rejected_returns_system_message() -> None:
    """
    If the remote swarm rejects a response, a system router message is returned.
    """
    registry = SwarmRegistry("example", "http://localhost:8000")
    registry.register_swarm("remote", "http://remote:9999", auth_token="token-remote")
    router = InterswarmRouter(registry, "example")
    router.session = _CaptureSession(
        [
            _SimpleResponse(
                200,
                json.dumps({"status": "no_mail_instance", "detail": "not ready"}),
            )
        ]
    )

    message = MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message={
            "task_id": "task-2",
            "request_id": "req-2",
            "sender": create_agent_address("supervisor"),
            "recipient": format_agent_address("supervisor", "remote"),
            "subject": "::task_complete::",
            "body": "Done",
            "sender_swarm": "example",
            "recipient_swarm": "remote",
            "routing_info": {},
        },
        msg_type="response",
    )

    result = await router._route_to_remote_swarm(
        message,
        "remote",
        is_response=True,
    )

    assert result["message"]["sender"]["address_type"] == "system"  # type: ignore[index]
    assert result["message"]["subject"] == "Router Error"  # type: ignore[index]
    assert "no_mail_instance" in result["message"]["body"]  # type: ignore[index]
