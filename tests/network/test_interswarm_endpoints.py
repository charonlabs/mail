# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from mail.core.message import (
    MAILInterswarmMessage,
    MAILMessage,
    MAILRequest,
    MAILResponse,
    create_agent_address,
    format_agent_address,
)


def _async_return(value):
    async def _inner():
        return value

    return _inner()


def _make_request_payload(task_id: str) -> MAILRequest:
    return MAILRequest(
        task_id=task_id,
        request_id=str(uuid.uuid4()),
        sender=format_agent_address("remote-agent", "remote"),
        recipient=create_agent_address("supervisor"),
        subject="Ping",
        body="Hello from remote",
        sender_swarm="remote",
        recipient_swarm="example",
        routing_info={},
    )


def _make_response_payload(task_id: str) -> MAILResponse:
    return MAILResponse(
        task_id=task_id,
        request_id=str(uuid.uuid4()),
        sender=format_agent_address("remote-agent", "remote"),
        recipient=create_agent_address("supervisor"),
        subject="::task_complete::",
        body="Done",
        sender_swarm="remote",
        recipient_swarm="example",
        routing_info={},
    )


def _wrap_interswarm(payload, msg_type: str) -> dict[str, object]:
    message = MAILInterswarmMessage(
        message_id=str(uuid.uuid4()),
        source_swarm="remote",
        target_swarm="example",
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        payload=payload,
        msg_type=msg_type,  # type: ignore
        auth_token="token-remote",
        task_owner="agent:remote@remote",
        task_contributors=["agent:remote@remote"],
        metadata={},
    )
    wrapper = dict(message)
    # Current server implementation expects task_id at top level.
    wrapper["task_id"] = payload["task_id"]  # type: ignore[index]
    return wrapper


@pytest.mark.usefixtures("patched_server")
def test_interswarm_forward_submits_to_runtime(monkeypatch: pytest.MonkeyPatch):
    """
    Test that the interswarm forward endpoint submits to the runtime when receiving an interswarm message.
    """
    from mail.server import app

    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return(
            {"role": "agent", "id": "ag-forward", "api_key": "api-key-forward"}
        ),
    )

    captured: dict[str, object] = {}

    class DummySwarm:
        async def receive_interswarm_message(  # noqa: D401
            self,
            message: MAILInterswarmMessage,
            direction: str = "forward",
        ) -> None:
            captured["message"] = message
            captured["direction"] = direction

    async def fake_get_or_create(role, identifier, api_key):  # noqa: ANN001
        return DummySwarm()

    monkeypatch.setattr(
        "mail.server.get_or_create_mail_instance",
        fake_get_or_create,
    )

    try:
        app.state.task_bindings
    except AttributeError:
        app.state.task_bindings = {}

    payload = _make_request_payload(task_id="task-forward")
    wrapper = _wrap_interswarm(payload, "request")

    with TestClient(app) as client:
        response = client.post(
            "/interswarm/forward",
            headers={"Authorization": "Bearer remote-token"},
            json={"message": wrapper},
        )

    assert response.status_code == 200, response.json()
    assert captured["direction"] == "forward"
    captured_message = captured["message"]
    assert isinstance(captured_message, dict)
    assert captured_message["payload"]["task_id"] == "task-forward"  # type: ignore[index]
    binding = app.state.task_bindings.get("task-forward")
    assert binding is not None
    assert binding["id"] == "ag-forward"


@pytest.mark.usefixtures("patched_server")
def test_interswarm_back_requires_running_task(monkeypatch: pytest.MonkeyPatch):
    """
    Test that the interswarm back endpoint requires a running task when receiving an interswarm message.
    """
    from mail.server import app

    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return(
            {"role": "agent", "id": "ag-back", "api_key": "api-key-back"}
        ),
    )

    payload = _make_response_payload(task_id="task-missing")
    wrapper = _wrap_interswarm(payload, "response")

    with TestClient(app) as client:
        response = client.post(
            "/interswarm/back",
            headers={"Authorization": "Bearer remote-token"},
            json={"message": wrapper},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "task is not running"


@pytest.mark.usefixtures("patched_server")
def test_interswarm_back_submits_to_runtime(monkeypatch: pytest.MonkeyPatch):
    """
    Test that the interswarm back endpoint submits to the runtime when the task is running.
    """
    from mail.server import app

    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return(
            {"role": "agent", "id": "ag-back", "api_key": "api-key-back"}
        ),
    )

    captured: dict[str, object] = {}

    class DummySwarm:
        async def receive_interswarm_message(  # noqa: D401
            self,
            message: MAILInterswarmMessage,
            direction: str = "back",
        ) -> None:
            captured["message"] = message
            captured["direction"] = direction

    def fake_get_mail_instance_from_interswarm_message(app, message):  # noqa: ANN001
        return DummySwarm()

    monkeypatch.setattr(
        "mail.server._get_mail_instance_from_interswarm_message",
        fake_get_mail_instance_from_interswarm_message,
    )

    forward_payload = _make_request_payload(task_id="task-running")
    forward_wrapper = _wrap_interswarm(forward_payload, "request")
    payload = _make_response_payload(task_id="task-running")
    wrapper = _wrap_interswarm(payload, "response")

    with TestClient(app) as client:
        forward_response = client.post(
            "/interswarm/forward",
            headers={"Authorization": "Bearer remote-token"},
            json={"message": forward_wrapper},
        )
        assert forward_response.status_code == 200, forward_response.json()

        response = client.post(
            "/interswarm/back",
            headers={"Authorization": "Bearer remote-token"},
            json={"message": wrapper},
        )

    result = response.json()
    assert response.status_code == 200, result
    assert captured["direction"] == "back"
    captured_message = captured["message"]
    assert isinstance(captured_message, dict)
    assert captured_message["payload"]["task_id"] == "task-running"  # type: ignore[index]


@pytest.mark.usefixtures("patched_server")
def test_post_interswarm_message_forwards_to_router(monkeypatch: pytest.MonkeyPatch):
    """
    Test that the interswarm message endpoint forwards to the router when receiving a message.
    """
    from mail.server import app

    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return(
            {"role": "user", "id": "user-123", "api_key": "api-key-user"}
        ),
    )

    captured: dict[str, MAILInterswarmMessage] = {}

    class DummyMail:
        enable_interswarm = True

        async def post_interswarm_user_message(  # noqa: D401
            self,
            message: MAILInterswarmMessage,
        ) -> MAILMessage:
            captured["message"] = message
            return MAILMessage(
                id=str(uuid.uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=_make_response_payload(task_id=message["payload"]["task_id"]),  # type: ignore[index]
                msg_type="response",
            )

    async def fake_get_or_create(role, identifier, api_key):  # noqa: ANN001
        return DummyMail()

    monkeypatch.setattr(
        "mail.server.get_or_create_mail_instance",
        fake_get_or_create,
    )

    with TestClient(app) as client:
        payload = {
            "targets": ["helper@remote"],
            "body": "Hello remote",
            "subject": "Custom Subject",
            "msg_type": "request",
            "task_id": "task-user",
            "user_token": "token-user",
            "routing_info": {"foo": "bar"},
        }

        response = client.post(
            "/interswarm/message",
            headers={"Authorization": "Bearer api-key"},
            json=payload,
        )

    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["response"]["msg_type"] == "response"

    delivered = captured["message"]
    assert delivered["payload"]["task_id"] == "task-user"  # type: ignore[index]
    assert delivered["payload"]["subject"] == "Custom Subject"  # type: ignore[index]
    assert delivered["payload"]["sender"]["address"] == "user-123"  # type: ignore[index]
