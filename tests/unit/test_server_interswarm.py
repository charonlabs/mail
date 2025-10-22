# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import json
import uuid

import pytest
from starlette.requests import Request

from mail.core.message import MAILMessage, MAILResponse, create_agent_address
from mail.server import app, receive_interswarm_back, utils


class DummyMailInstance:
    def __init__(self) -> None:
        self.messages: list[MAILMessage] = []

    async def handle_interswarm_response(self, message: MAILMessage) -> None:
        self.messages.append(message)


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


@pytest.mark.asyncio
async def test_interswarm_response_routes_to_task_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    When an interswarm response is received, it should be routed to the task owner.
    """
    from mail import server

    task_id = "task-bind"
    binding = {"role": "user", "id": "user-123", "jwt": "user-jwt"}

    dummy_instance = DummyMailInstance()

    monkeypatch.setattr(server.app.state, "task_bindings", {task_id: binding}, raising=False)
    monkeypatch.setattr(server.app.state, "user_mail_instances", {}, raising=False)
    monkeypatch.setattr(server.app.state, "user_mail_tasks", {}, raising=False)
    monkeypatch.setattr(server.app.state, "swarm_mail_instances", {}, raising=False)
    monkeypatch.setattr(server.app.state, "swarm_mail_tasks", {}, raising=False)
    monkeypatch.setattr(server.app.state, "local_swarm_name", "alpha", raising=False)
    monkeypatch.setattr(server.app.state, "local_base_url", "http://localhost", raising=False)

    async def fake_get_or_create(role: str, identifier: str, jwt: str):
        assert role == "user"
        assert identifier == "user-123"
        assert jwt == "user-jwt"
        server.app.state.user_mail_instances[identifier] = dummy_instance
        return dummy_instance

    monkeypatch.setattr(server, "get_or_create_mail_instance", fake_get_or_create)
    monkeypatch.setattr(utils, "extract_token", lambda request: "remote-token")

    response_message: MAILMessage = MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message=MAILResponse(
            task_id=task_id,
            request_id=str(uuid.uuid4()),
            sender=create_agent_address("remote@swarm-beta"),
            recipient=create_agent_address("supervisor"),
            subject="Status",
            body="done",
            sender_swarm="swarm-beta",
            recipient_swarm="swarm-alpha",
            routing_info={},
        ),
        msg_type="response",
    )

    request = _build_request(dict(response_message))
    result = await receive_interswarm_back(request)

    assert result["swarm"] == "swarm-alpha"
    assert result["task_id"] == task_id
    assert result["status"] == "ok"
    assert result["local_runner"] == "user-123@swarm-alpha"
    assert dummy_instance.messages and dummy_instance.messages[0]["message"]["body"] == "done"

