# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import json
import uuid
from typing import Any

import pytest
from starlette.requests import Request

from mail.core.message import (
    MAILInterswarmMessage,
    MAILResponse,
    create_agent_address,
)
from mail.server import app, receive_interswarm_back, utils


class DummyMailInstance:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def receive_interswarm_message(
        self, message: dict[str, Any], *, direction: str
    ) -> None:
        self.messages.append({"message": message, "direction": direction})


def _build_request(body: dict[str, object]) -> Request:
    payload = json.dumps(body).encode("utf-8")
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"authorization", b"Bearer remote-token")],
        "path": "/interswarm/back",
        "app": app,
    }

    async def receive() -> dict[str, object]:
        nonlocal payload
        if payload:
            chunk = payload
            payload = b""
            return {"type": "http.request", "body": chunk, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)  # type: ignore[arg-type]


async def _extract_token_info(request: Request) -> dict[str, Any]:
    return {"id": "swarm-beta", "api_key": "remote-api-key", "role": "agent"}


@pytest.mark.asyncio
async def test_interswarm_response_routes_to_task_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When an interswarm response is received, it should be routed to the task owner.
    """
    from mail import server

    task_id = "task-bind"
    binding = {"role": "user", "id": "user-123", "api_key": "user-api-key"}

    dummy_instance = DummyMailInstance()

    monkeypatch.setattr(
        server.app.state, "task_bindings", {task_id: binding}, raising=False
    )
    monkeypatch.setattr(server.app.state, "user_mail_instances", {}, raising=False)
    monkeypatch.setattr(server.app.state, "user_mail_tasks", {}, raising=False)
    monkeypatch.setattr(server.app.state, "swarm_mail_instances", {}, raising=False)
    monkeypatch.setattr(server.app.state, "swarm_mail_tasks", {}, raising=False)
    monkeypatch.setattr(
        server.app.state, "local_swarm_name", "swarm-alpha", raising=False
    )
    monkeypatch.setattr(
        server.app.state, "local_base_url", "http://localhost", raising=False
    )

    def fake_get_mail_instance_from_interswarm_message(app, message):  # noqa: ANN001
        return dummy_instance

    monkeypatch.setattr(
        server,
        "_get_mail_instance_from_interswarm_message",
        fake_get_mail_instance_from_interswarm_message,
    )
    monkeypatch.setattr(utils, "extract_token_info", _extract_token_info)

    response_payload: MAILResponse = MAILResponse(
        task_id=task_id,
        request_id=str(uuid.uuid4()),
        sender=create_agent_address("remote@swarm-beta"),
        recipient=create_agent_address("supervisor"),
        subject="Status",
        body="done",
        sender_swarm="swarm-beta",
        recipient_swarm="swarm-alpha",
        routing_info={},
    )

    base_interswarm: MAILInterswarmMessage = MAILInterswarmMessage(
        message_id=str(uuid.uuid4()),
        source_swarm="swarm-beta",
        target_swarm="swarm-alpha",
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        payload=response_payload,
        msg_type="response",
        auth_token="remote-token",
        task_owner="user:user-123@swarm-alpha",
        task_contributors=["user:user-123@swarm-alpha", "agent:remote@swarm-beta"],
        metadata={},
    )
    interswarm_message: dict[str, Any] = dict(base_interswarm)
    interswarm_message["task_id"] = task_id

    request = _build_request({"message": interswarm_message})
    result = await receive_interswarm_back(request)

    assert result["swarm"] == "swarm-alpha"
    assert result["task_id"] == task_id
    assert result["status"] == "success"
    assert result["local_runner"] == "swarm:swarm-beta@swarm-alpha"
    assert dummy_instance.messages
    recorded = dummy_instance.messages[0]
    assert recorded["direction"] == "back"
    assert recorded["message"]["payload"]["body"] == "done"
