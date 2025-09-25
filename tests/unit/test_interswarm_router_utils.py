# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import uuid

from mail.core.message import (
    MAILMessage,
    MAILRequest,
    create_agent_address,
    format_agent_address,
)
from mail.net.router import InterswarmRouter


class _DummyRegistry:
    def get_swarm_endpoint(self, name):  # noqa: ANN001
        return {"swarm_name": name, "base_url": "http://x", "is_active": True}

    def get_active_endpoints(self):  # noqa: ANN001
        return {"example": {"is_active": True}, "remote": {"is_active": True}}


def _base_request():
    return MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message=MAILRequest(
            task_id="t1",
            request_id="r1",
            sender=create_agent_address("supervisor"),
            recipient=create_agent_address("analyst"),
            subject="S",
            body="B",
            sender_swarm=None,
            recipient_swarm=None,
            routing_info={},
        ),
        msg_type="request",
    )


def test_determine_message_type_mapping():
    """
    Test that `_determine_message_type` works as expected.
    """
    router = InterswarmRouter(_DummyRegistry(), "example")
    assert (
        router._determine_message_type({"request_id": "r", "recipient": {}})
        == "request"
    )
    assert (
        router._determine_message_type({"request_id": "r", "sender": {}}) == "response"
    )
    assert router._determine_message_type({"broadcast_id": "b"}) == "broadcast"
    assert router._determine_message_type({"interrupt_id": "i"}) == "interrupt"
    assert router._determine_message_type({}) == "unknown"


def test_create_local_and_remote_message_shapes():
    """
    Test that `_create_local_message` and `_create_remote_message` work as expected.
    """
    router = InterswarmRouter(_DummyRegistry(), "example")

    original = MAILMessage(
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
            "subject": "hello",
            "body": "world",
            "sender_swarm": None,
            "recipient_swarms": None,
            "routing_info": {},
        },
        msg_type="broadcast",
    )

    local = router._create_local_message(original, ["analyst"])
    assert "recipients" in local["message"]
    addrs = [a["address"] for a in local["message"]["recipients"]]  # type: ignore
    assert addrs == ["analyst"]

    remote = router._create_remote_message(original, ["helper"], "remote")
    assert "recipients" in remote["message"]
    addrs_r = [a["address"] for a in remote["message"]["recipients"]]  # type: ignore
    assert addrs_r == ["helper@remote"]
    assert remote["message"]["sender_swarm"] == "example"  # type: ignore


def test_system_router_message_is_response():
    """
    Test that `_system_router_message` works as expected.
    """
    router = InterswarmRouter(_DummyRegistry(), "example")
    original = _base_request()
    out = router._system_router_message(original, "oops")
    assert out["msg_type"] == "response"
    assert out["message"]["subject"] == "Router Error"  # type: ignore
