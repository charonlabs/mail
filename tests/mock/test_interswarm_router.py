# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import uuid

import pytest

from mail.core.message import (
    MAILInterswarmMessage,
    MAILRequest,
    create_agent_address,
    format_agent_address,
)
from mail.net.registry import SwarmRegistry
from mail.net.router import InterswarmRouter


def _make_interswarm_request(
    *,
    target_swarm: str,
    recipient: str = "analyst",
) -> MAILInterswarmMessage:
    """
    Build a minimal interswarm request wrapper for tests.
    """
    payload = MAILRequest(
        task_id="task-1",
        request_id="req-1",
        sender=create_agent_address("supervisor"),
        recipient=format_agent_address(recipient, target_swarm),
        subject="Subject",
        body="Body",
        sender_swarm="local",
        recipient_swarm=target_swarm,
        routing_info={},
    )
    return MAILInterswarmMessage(
        message_id=str(uuid.uuid4()),
        source_swarm="local",
        target_swarm=target_swarm,
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        payload=payload,
        msg_type="request",
        auth_token="token-local",
        task_owner="user:123@local",
        task_contributors=["user:123@local"],
        metadata={},
    )


class _DummyResponse:
    def __init__(self, status: int, *, reason: str = "OK") -> None:
        self.status = status
        self.reason = reason

    async def __aenter__(self) -> "_DummyResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[override]
        return False


class _DummySession:
    def __init__(self, responses: list["_DummyResponse"]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        json: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> "_DummyResponse":
        if not self._responses:
            raise AssertionError("no responses configured")
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_receive_interswarm_forward_dispatches_to_handler() -> None:
    """
    Test that the interswarm router dispatches to the local message handler when receiving an interswarm message for the local swarm.
    """
    registry = SwarmRegistry("local", "http://localhost:8000")
    router = InterswarmRouter(registry, "local")

    received: list[MAILInterswarmMessage] = []

    async def handler(message: MAILInterswarmMessage) -> None:
        received.append(message)

    router.register_message_handler("local_message_handler", handler)

    message = _make_interswarm_request(target_swarm="local")
    await router.receive_interswarm_message_forward(message)

    assert received == [message]


@pytest.mark.asyncio
async def test_receive_interswarm_forward_wrong_swarm_raises() -> None:
    """
    Test that the interswarm router raises an error when receiving an interswarm message for the wrong swarm.
    """
    registry = SwarmRegistry("local", "http://localhost:8000")
    router = InterswarmRouter(registry, "local")

    message = _make_interswarm_request(target_swarm="remote")

    with pytest.raises(ValueError):
        await router.receive_interswarm_message_forward(message)


@pytest.mark.asyncio
async def test_receive_interswarm_back_dispatches_to_handler() -> None:
    """
    Test that the interswarm router dispatches to the local message handler when receiving an interswarm message for the local swarm.
    """
    registry = SwarmRegistry("local", "http://localhost:8000")
    router = InterswarmRouter(registry, "local")

    received: list[MAILInterswarmMessage] = []

    async def handler(message: MAILInterswarmMessage) -> None:
        received.append(message)

    router.register_message_handler("local_message_handler", handler)

    message = _make_interswarm_request(target_swarm="local")
    await router.receive_interswarm_message_back(message)

    assert received == [message]


@pytest.mark.asyncio
async def test_send_interswarm_message_forward_posts_to_forward_endpoint() -> None:
    """
    Test that the interswarm router posts to the forward endpoint when sending an interswarm message to a remote swarm.
    """
    registry = SwarmRegistry("local", "http://localhost:8000")
    registry.register_swarm("remote", "http://remote:9999", auth_token="token-remote")
    router = InterswarmRouter(registry, "local")

    router.session = _DummySession([_DummyResponse(200)])  # type: ignore[assignment]

    message = _make_interswarm_request(target_swarm="remote")

    await router.send_interswarm_message_forward(message)

    assert router.session.calls # type: ignore
    call = router.session.calls[0] # type: ignore
    assert call["url"] == "http://remote:9999/interswarm/forward"
    headers = call["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer None"


@pytest.mark.asyncio
async def test_send_interswarm_message_back_posts_to_back_endpoint() -> None:
    """
    Test that the interswarm router posts to the back endpoint when sending an interswarm message to a remote swarm.
    """
    registry = SwarmRegistry("local", "http://localhost:8000")
    registry.register_swarm("remote", "http://remote:9999", auth_token="token-remote")
    router = InterswarmRouter(registry, "local")

    router.session = _DummySession([_DummyResponse(200)])  # type: ignore[assignment]

    message = _make_interswarm_request(target_swarm="remote")

    await router.send_interswarm_message_back(message)

    assert router.session.calls # type: ignore
    call = router.session.calls[0] # type: ignore
    assert call["url"] == "http://remote:9999/interswarm/back"
    headers = call["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer None"
