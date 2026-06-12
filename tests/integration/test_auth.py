# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from mail_server.auth import create_access_token

ADMIN = "admin:ryan@localhost"
USER = "user:alice@localhost"
AGENT = "sage@chorus@localhost"
DAEMON = "daemon:dummy@localhost"
PASSWORD = "correct-horse-battery-staple"


# ─── POST /auth/token ──────────────────────────────────────────────


@pytest.mark.parametrize("address", [ADMIN, USER, AGENT, DAEMON])
def test_token_issued_for_every_role(app_client: TestClient, address: str) -> None:
    response = app_client.post(
        "/auth/token",
        data={"username": address, "password": PASSWORD},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]


def test_token_rejects_wrong_password(app_client: TestClient) -> None:
    response = app_client.post(
        "/auth/token",
        data={"username": USER, "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_token_rejects_unknown_address(app_client: TestClient) -> None:
    response = app_client.post(
        "/auth/token",
        data={"username": "user:ghost@localhost", "password": PASSWORD},
    )
    assert response.status_code == 401


# ─── GET /auth/whoami ──────────────────────────────────────────────


def test_whoami_returns_authenticated_identity(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get("/auth/whoami", headers=headers_for(USER))
    assert response.status_code == 200
    user_agent = response.json()["user_agent"]["user_agent"]
    assert user_agent["ua_type"] == "user"
    assert user_agent["user_id"] == "alice"


def test_whoami_does_not_leak_hashed_password(
    app_client: TestClient, headers_for
) -> None:
    """
    The backend stores MAILUserAgentInBackend (which carries
    hashed_password); the whoami response model must filter it out.
    """

    response = app_client.get("/auth/whoami", headers=headers_for(USER))
    assert response.status_code == 200
    assert "hashed_password" not in response.text


def test_whoami_rejects_missing_token(app_client: TestClient) -> None:
    response = app_client.get("/auth/whoami")
    assert response.status_code == 401


def test_whoami_rejects_garbage_token(app_client: TestClient) -> None:
    response = app_client.get(
        "/auth/whoami",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401


def test_whoami_rejects_expired_token(app_client: TestClient) -> None:
    expired = create_access_token(
        data={"sub": USER}, expires_delta=timedelta(minutes=-5)
    )
    response = app_client.get(
        "/auth/whoami",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert response.status_code == 401


def test_whoami_rejects_token_without_subject(app_client: TestClient) -> None:
    subjectless = create_access_token(data={})
    response = app_client.get(
        "/auth/whoami",
        headers={"Authorization": f"Bearer {subjectless}"},
    )
    assert response.status_code == 401


def test_whoami_rejects_token_for_deleted_user_agent(
    app_client: TestClient,
) -> None:
    """A valid JWT whose subject was since deleted must 401, not 500."""

    orphaned = create_access_token(data={"sub": "user:ghost@localhost"})
    response = app_client.get(
        "/auth/whoami",
        headers={"Authorization": f"Bearer {orphaned}"},
    )
    assert response.status_code == 401


# ─── POST /auth/password/reset ─────────────────────────────────────


def test_password_reset_roundtrip(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/auth/password/reset",
        json={"current_password": PASSWORD, "new_password": "a-new-password"},
        headers=headers_for(USER),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # The old password no longer authenticates; the new one does.
    response = app_client.post(
        "/auth/token", data={"username": USER, "password": PASSWORD}
    )
    assert response.status_code == 401
    response = app_client.post(
        "/auth/token", data={"username": USER, "password": "a-new-password"}
    )
    assert response.status_code == 200


def test_password_reset_rejects_wrong_current_password(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/auth/password/reset",
        json={"current_password": "wrong", "new_password": "a-new-password"},
        headers=headers_for(USER),
    )
    assert response.status_code == 401


def test_password_reset_rejects_malformed_body(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/auth/password/reset",
        json={"current_password": PASSWORD},
        headers=headers_for(USER),
    )
    assert response.status_code == 422
