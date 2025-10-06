# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sse_starlette import EventSourceResponse, ServerSentEvent

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


@pytest.mark.usefixtures("patched_server")
def test_interswarm_message_success(monkeypatch: pytest.MonkeyPatch):
    """
    Test that `POST /interswarm/message` works as expected.
    """
    from mail.server import app

    # Make auth treat caller as agent for interswarm paths
    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return({"role": "agent", "id": "ag-123"}),
    )

    with TestClient(app) as client:
        payload: MAILRequest = MAILRequest(
            task_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            sender=format_agent_address("remote-agent", "remote"),
            recipient=create_agent_address("supervisor"),
            subject="Ping",
            body="Hello from remote",
            sender_swarm="remote",
            recipient_swarm="example",
            routing_info={},
        )
        wrapper: MAILInterswarmMessage = MAILInterswarmMessage(
            message_id=str(uuid.uuid4()),
            source_swarm="remote",
            target_swarm="example",
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            payload=payload,
            msg_type="request",
            auth_token="token-123",
            metadata={"expect_response": True},
        )

        r = client.post(
            "/interswarm/message",
            headers={"Authorization": "Bearer test-key"},
            json=wrapper,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["msg_type"] == "response"
        # Response recipient should be original sender
        assert data["message"]["recipient"]["address"] == payload["sender"]["address"]


@pytest.mark.usefixtures("patched_server")
def test_interswarm_message_streaming_response(monkeypatch: pytest.MonkeyPatch):
    """
    Verify that streaming metadata returns an SSE response with task events.
    """
    from mail.server import app

    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return({"role": "agent", "id": "ag-stream"}),
    )

    captured_ping: list[int | None] = []

    async def fake_stream(
        self,
        message,
        timeout: float = 3600.0,
        resume_from=None,
        *,
        ping_interval: int | None = 15000,
        **kwargs,
    ):
        task_id = message["message"]["task_id"]
        captured_ping.append(ping_interval)

        async def event_gen():
            yield ServerSentEvent(
                event="new_message",
                data={
                    "task_id": task_id,
                    "extra_data": {"full_message": message},
                },
            )
            yield ServerSentEvent(
                event="task_complete",
                data={"task_id": task_id, "response": "done"},
            )

        return EventSourceResponse(event_gen(), ping=ping_interval)

    monkeypatch.setattr("mail.MAILSwarm.submit_message_stream", fake_stream, raising=True)

    with TestClient(app) as client:
        payload: MAILRequest = MAILRequest(
            task_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            sender=format_agent_address("remote-agent", "remote"),
            recipient=create_agent_address("supervisor"),
            subject="Ping",
            body="Hello from remote",
            sender_swarm="remote",
            recipient_swarm="example",
            routing_info={"stream": True},
        )
        wrapper: MAILInterswarmMessage = MAILInterswarmMessage(
            message_id=str(uuid.uuid4()),
            source_swarm="remote",
            target_swarm="example",
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            payload=payload,
            msg_type="request",
            auth_token="token-123",
            metadata={"expect_response": True, "stream": True},
        )

        with client.stream(
            "POST",
            "/interswarm/message",
            headers={"Authorization": "Bearer test-key"},
            json=wrapper,
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            raw_events: list[str] = []
            for line in response.iter_lines():
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8")
                raw_events.append(line.strip())

        assert any(
            line.startswith("event:new_message") or line.startswith("event: new_message")
            for line in raw_events
        )
        assert any(
            line.startswith("event:task_complete") or line.startswith("event: task_complete")
            for line in raw_events
        )

        data_lines = [line for line in raw_events if line.startswith("data:")]
        assert any(payload["task_id"] in line for line in data_lines)
        assert captured_ping == [15000]


@pytest.mark.usefixtures("patched_server")
def test_interswarm_message_streaming_ignores_pings(monkeypatch: pytest.MonkeyPatch):
    """
    Ensure that `ignore_stream_pings` disables heartbeat emission.
    """
    from mail.server import app

    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return({"role": "agent", "id": "ag-no-ping"}),
    )

    captured_ping: list[int | None] = []

    async def fake_stream(
        self,
        message,
        timeout: float = 3600.0,
        resume_from=None,
        *,
        ping_interval: int | None = 15000,
        **kwargs,
    ):
        captured_ping.append(ping_interval)

        async def event_gen():
            yield ServerSentEvent(
                event="task_complete",
                data={"task_id": message["message"]["task_id"], "response": "ok"},
            )

        return EventSourceResponse(event_gen(), ping=ping_interval)

    monkeypatch.setattr("mail.MAILSwarm.submit_message_stream", fake_stream, raising=True)

    with TestClient(app) as client:
        payload: MAILRequest = MAILRequest(
            task_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            sender=format_agent_address("remote-agent", "remote"),
            recipient=create_agent_address("supervisor"),
            subject="Ping",
            body="Hello from remote",
            sender_swarm="remote",
            recipient_swarm="example",
            routing_info={"stream": True, "ignore_stream_pings": True},
        )
        wrapper: MAILInterswarmMessage = MAILInterswarmMessage(
            message_id=str(uuid.uuid4()),
            source_swarm="remote",
            target_swarm="example",
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            payload=payload,
            msg_type="request",
            auth_token="token-123",
            metadata={
                "expect_response": True,
                "stream": True,
                "ignore_stream_pings": True,
            },
        )

        with client.stream(
            "POST",
            "/interswarm/message",
            headers={"Authorization": "Bearer test-key"},
            json=wrapper,
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events: list[str] = []
            for line in response.iter_lines():
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8")
                events.append(line.strip())

        assert captured_ping == [None]
        assert any(
            line.startswith("event:task_complete") or line.startswith("event: task_complete")
            for line in events
        )


@pytest.mark.usefixtures("patched_server")
def test_interswarm_send_custom_request(monkeypatch: pytest.MonkeyPatch):
    """
    Users can customize subject, msg_type, and routing flags when sending interswarm messages.
    """
    from mail.server import app, user_mail_instances

    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return({"role": "user", "id": "user-123"}),
    )

    captured: dict[str, MAILMessage] = {}

    class DummyMail:
        enable_interswarm = True

        async def route_interswarm_message(self, message: MAILMessage) -> MAILMessage:
            captured["message"] = message
            return message
        
        async def shutdown(self) -> None:
            pass

    user_mail_instances["test-token"] = DummyMail() # type: ignore[assignment]

    with TestClient(app) as client:
        payload = {
            "targets": ["helper@remote"],
            "body": "Hello remote",
            "subject": "Custom Subject",
            "msg_type": "request",
            "task_id": "task-xyz",
            "stream": True,
            "ignore_stream_pings": True,
            "routing_info": {"foo": "bar"},
            "user_token": "test-token",
        }

        r = client.post(
            "/interswarm/send",
            headers={"Authorization": "Bearer test-key"},
            json=payload,
        )

        assert r.status_code == 200
        assert "message" in captured
        message = captured["message"]
        assert message["msg_type"] == "request"
        assert message["message"]["subject"] == "Custom Subject"
        assert message["message"]["body"] == "Hello remote"
        assert message["message"]["task_id"] == "task-xyz"
        assert message["message"]["routing_info"]["foo"] == "bar" # type: ignore
        assert message["message"]["routing_info"]["stream"] is True # type: ignore
        assert message["message"]["routing_info"]["ignore_stream_pings"] is True # type: ignore
        assert message["message"]["recipient"]["address"] == "helper@remote" # type: ignore
        assert message["message"]["recipient_swarm"] == "remote" # type: ignore


@pytest.mark.usefixtures("patched_server")
def test_interswarm_send_broadcast(monkeypatch: pytest.MonkeyPatch):
    """
    Users can send broadcast interswarm messages to multiple targets.
    """
    from mail.server import app, user_mail_instances

    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return({"role": "user", "id": "user-456"}),
    )

    captured: dict[str, MAILMessage] = {}

    class DummyMAILInstance:
        enable_interswarm = True

        async def route_interswarm_message(self, message: MAILMessage) -> MAILMessage:
            captured["message"] = message
            return message

        async def shutdown(self) -> None:
            pass

    user_mail_instances["token-broadcast"] = DummyMAILInstance() # type: ignore[assignment]

    with TestClient(app) as client:
        payload = {
            "targets": ["helper@remote", "analyst"],
            "body": "Broadcast body",
            "subject": "Broadcast",
            "msg_type": "broadcast",
            "user_token": "token-broadcast",
        }

        r = client.post(
            "/interswarm/send",
            headers={"Authorization": "Bearer test-key"},
            json=payload,
        )

        assert r.status_code == 200
        message = captured["message"]
        assert message["msg_type"] == "broadcast"
        recipients = message["message"]["recipients"]  # type: ignore
        addresses = {recipient["address"] for recipient in recipients}
        assert addresses == {"helper@remote", "analyst"}
        assert "remote" in message["message"]["recipient_swarms"]  # type: ignore


@pytest.mark.usefixtures("patched_server")
def test_interswarm_send_invalid_msg_type(monkeypatch: pytest.MonkeyPatch):
    """
    Unsupported message types should return a 400 error.
    """
    from mail.server import app, user_mail_instances

    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return({"role": "user", "id": "user-789"}),
    )

    class DummyMAILInstance:
        enable_interswarm = True

        async def route_interswarm_message(self, message: MAILMessage) -> MAILMessage:  # noqa: ARG002
            return message

        async def shutdown(self) -> None:
            pass

    user_mail_instances["token-invalid"] = DummyMAILInstance() # type: ignore[assignment]

    with TestClient(app) as client:
        payload = {
            "targets": ["helper@remote"],
            "body": "Body",
            "msg_type": "interrupt",
            "user_token": "token-invalid",
        }

        r = client.post(
            "/interswarm/send",
            headers={"Authorization": "Bearer test-key"},
            json=payload,
        )

        assert r.status_code == 400
        assert "not supported" in r.json()["detail"]


@pytest.mark.usefixtures("patched_server")
def test_interswarm_response_no_mail_instance(monkeypatch: pytest.MonkeyPatch):
    """
    Test that `POST /interswarm/response` works as expected when there is no MAIL instance.
    """
    from mail.server import app

    # Treat caller as agent
    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return({"role": "agent", "id": "ag-999"}),
    )

    with TestClient(app) as client:
        response_msg: MAILMessage = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILResponse(
                task_id="task-nope",
                request_id="req-nope",
                sender=format_agent_address("remote-agent", "remote"),
                recipient=create_agent_address("supervisor"),
                subject="Reply",
                body="Body",
                sender_swarm="remote",
                recipient_swarm="example",
                routing_info={},
            ),
            msg_type="response",
        )

        r = client.post(
            "/interswarm/response",
            headers={"Authorization": "Bearer test-key"},
            json=response_msg,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "no_mail_instance"
        assert data["task_id"] == "task-nope"


@pytest.mark.usefixtures("patched_server")
def test_interswarm_message_requires_agent_role():
    """
    Test that `POST /interswarm/message` requires the `agent` role.
    """
    from mail.server import app

    with TestClient(app) as client:
        # Using default patched get_token_info which returns role=user
        r = client.post(
            "/interswarm/message",
            headers={"Authorization": "Bearer test-key"},
            json={"msg_type": "request"},
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "invalid role"
