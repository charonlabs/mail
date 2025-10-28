# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.mark.usefixtures("patched_server")
def test_root_endpoint():
    """
    Test that `GET /` works as expected.
    """
    from mail.server import app

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "mail"
        assert data["status"] == "running"


@pytest.mark.usefixtures("patched_server")
def test_status_without_auth():
    """
    Test that `GET /status` requires an authorization header.
    """
    from mail.server import app

    with TestClient(app) as client:
        r = client.get("/status")
        assert r.status_code == 401


@pytest.mark.usefixtures("patched_server")
def test_status_with_auth():
    """
    Test that `GET /status` works as expected with an authorization header.
    """
    from mail.server import app

    with TestClient(app) as client:
        r = client.get("/status", headers={"Authorization": "Bearer test-key"})
        assert r.status_code == 200
        data = r.json()
        assert data["swarm"]["status"] == "ready"
        assert data["user_mail_ready"] is False


@pytest.mark.usefixtures("patched_server")
def test_message_flow_success():
    """
    Test that `POST /message` works as expected.
    """
    from mail.server import app

    with TestClient(app) as client:
        r = client.post(
            "/message",
            headers={"Authorization": "Bearer test-key"},
            json={
                "subject": "Hello",
                "body": "Hello",
                "msg_type": "request",
                "task_id": "test-task-id",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["response"] is not None


@pytest.mark.usefixtures("patched_server")
def test_post_responses_requires_debug():
    """
    `POST /responses` should be hidden when debug mode is disabled.
    """
    from mail.server import app

    with TestClient(app) as client:
        app.state.debug = False
        response = client.post(
            "/responses",
            json={"api_key": "test-key", "input": [], "tools": []},
        )
        assert response.status_code == 404


@pytest.mark.usefixtures("patched_server")
def test_post_responses_validates_payload():
    """
    `POST /responses` should reject payloads with the wrong schema.
    """
    from mail.server import app

    with TestClient(app) as client:
        app.state.debug = True
        response = client.post(
            "/responses",
            json={"api_key": "test-key", "input": "not-a-list", "tools": []},
        )
        assert response.status_code == 400
        assert response.json()["detail"].startswith("parameter 'input' must be a list")


@pytest.mark.usefixtures("patched_server")
def test_post_responses_calls_openai_client(monkeypatch: pytest.MonkeyPatch):
    """
    Happy path: the endpoint must forward the request to the OpenAI client.
    """
    from mail.server import app

    class DummyResponses:
        def __init__(self) -> None:
            self.called_with: dict[str, Any] | None = None

        async def create(self, **kwargs: Any) -> dict[str, Any]:
            self.called_with = kwargs
            return {"id": "resp-123", "output": [{"type": "message", "content": "ok"}]}

    class DummyOpenAIClient:
        def __init__(self) -> None:
            self.responses = DummyResponses()

    async def fake_get_token_info(token: str) -> dict[str, str]:
        assert token == "resp-api-key"
        return {"role": "user", "id": "u-456"}

    monkeypatch.setattr("mail.utils.get_token_info", fake_get_token_info, raising=False)
    monkeypatch.setattr(
        "mail.utils.auth.get_token_info", fake_get_token_info, raising=False
    )

    input_payload = [{"role": "user", "content": "hello"}]
    tools_payload = [{"type": "function", "function": {"name": "task_complete"}}]
    instructions = "Follow the spec."
    previous_response_id = "resp-111"
    tool_choice = "auto"
    parallel_tool_calls = False
    extra_kwargs = {"temperature": 0.4}

    with TestClient(app) as client:
        app.state.debug = True
        dummy_client = DummyOpenAIClient()
        app.state.openai_client = dummy_client
        response = client.post(
            "/responses",
            json={
                "api_key": "resp-api-key",
                "input": input_payload,
                "tools": tools_payload,
                "instructions": instructions,
                "previous_response_id": previous_response_id,
                "tool_choice": tool_choice,
                "parallel_tool_calls": parallel_tool_calls,
                "kwargs": extra_kwargs,
            },
        )

        assert response.status_code == 200
        assert response.json()["id"] == "resp-123"

        assert dummy_client.responses.called_with == {
            "input": input_payload,
            "tools": tools_payload,
            "instructions": instructions,
            "previous_response_id": previous_response_id,
            "tool_choice": tool_choice,
            "parallel_tool_calls": parallel_tool_calls,
            **extra_kwargs,
        }


@pytest.mark.usefixtures("patched_server")
def test_message_flow_defaults_msg_type_on_none():
    """
    The server should treat an explicit `null` message type as a request.
    """
    from mail.server import app

    with TestClient(app) as client:
        r = client.post(
            "/message",
            headers={"Authorization": "Bearer test-key"},
            json={
                "subject": "Hello",
                "body": "Hello",
                "msg_type": None,
                "task_id": "test-task-id",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["response"] is not None
