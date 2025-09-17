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


@pytest.mark.usefixtures("patched_server")
def test_interswarm_message_success(monkeypatch: pytest.MonkeyPatch):
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
def test_interswarm_response_no_mail_instance(monkeypatch: pytest.MonkeyPatch):
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
