# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import pytest
from fastapi.testclient import TestClient


def _async_return(value):
    async def _inner():
        return value

    return _inner()


@pytest.mark.usefixtures("patched_server")
def test_message_requires_auth_missing_header():
    """
    Test that `POST /message` requires an authorization header.
    """
    from mail.server import app

    with TestClient(app) as client:
        r = client.post(
            "/message",
            json={
                "subject": "Test",
                "body": "Hello",
                "msg_type": "request",
                "task_id": "test-task-id",
            },
        )
        assert r.status_code == 401
        assert r.json()["detail"] in ("no API key provided", "invalid API key format")


@pytest.mark.usefixtures("patched_server")
def test_message_invalid_auth_format():
    """
    Test that `POST /message` requires a valid authorization header.
    """
    from mail.server import app

    with TestClient(app) as client:
        r = client.post(
            "/message",
            headers={"Authorization": "invalid-token"},
            json={
                "subject": "Test",
                "body": "Hello",
                "msg_type": "request",
                "task_id": "test-task-id",
            },
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "invalid role"


@pytest.mark.usefixtures("patched_server")
def test_message_invalid_role_rejected(monkeypatch: pytest.MonkeyPatch):
    """
    Test that `POST /message` requires a non-`agent` role.
    """
    from mail.server import app

    # Override token info to mimic an agent (not a user/admin)
    monkeypatch.setattr(
        "mail.utils.auth.get_token_info",
        lambda token: _async_return({"role": "agent", "id": "a-1"}),
    )

    with TestClient(app) as client:
        r = client.post(
            "/message",
            headers={"Authorization": "Bearer test-key"},
            json={
                "subject": "Test",
                "body": "Hello",
                "msg_type": "request",
                "task_id": "test-task-id",
            },
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "invalid role"


@pytest.mark.usefixtures("patched_server")
def test_status_after_message_shows_user_ready_true(monkeypatch: pytest.MonkeyPatch):
    """
    Test that `GET /status` shows the user as ready after a message is sent.
    """
    from mail.server import app

    with TestClient(app) as client:
        # Initially, user is not active
        r0 = client.get("/status", headers={"Authorization": "Bearer test-key"})
        assert r0.status_code == 200
        assert r0.json()["user_mail_ready"] is False

        # Perform a successful chat (stubbed in fixture to complete tasks)
        rc = client.post(
            "/message",
            headers={"Authorization": "Bearer test-key"},
            json={
                "subject": "Test",
                "body": "Hello",
                "msg_type": "request",
                "task_id": "test-task-id",
            },
        )
        assert rc.status_code == 200

        # Now, user should be present/ready
        r1 = client.get("/status", headers={"Authorization": "Bearer test-key"})
        data = r1.json()
        assert data["user_mail_ready"] is True
        assert data["active_users"] >= 1
