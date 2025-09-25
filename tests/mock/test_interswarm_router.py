# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import uuid

import pytest

from mail.core.message import (
    MAILMessage,
    MAILRequest,
    create_agent_address,
    format_agent_address,
)
from mail.net.registry import SwarmRegistry
from mail.net.router import InterswarmRouter


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

    async def fake_remote(mm: MAILMessage, swarm: str):  # noqa: ANN001
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
