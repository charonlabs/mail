# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""OAuth grants and request-time authorization for daemon scopes."""

import jwt
import pytest
from fastapi.testclient import TestClient
from mail_server import auth

ADMIN = "admin:ryan@localhost"
USER = "user:alice@localhost"
DAEMON = "daemon:dummy@localhost"
PASSWORD = "correct-horse-battery-staple"


def _login(
    client: TestClient,
    address: str,
    *,
    password: str = PASSWORD,
    scope: str = "",
):
    return client.post(
        "/auth/token",
        data={"username": address, "password": password, "scope": scope},
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_daemon(
    client: TestClient,
    headers_for,
    *,
    worker_name: str,
    scopes: list[str],
) -> tuple[str, str]:
    password = f"{worker_name}-password"
    response = client.post(
        "/admin/daemons",
        json={
            "worker_name": worker_name,
            "daemon_password": password,
            "scopes": scopes,
        },
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 200, response.text
    return f"daemon:{worker_name}@localhost", password


def _create_draft(client: TestClient, token: str) -> str:
    response = client.post(
        "/drafts",
        json={"subject": "Scoped delivery", "body": "scope test"},
        headers=_bearer(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["entry"]["draft"]["draft_id"]


def test_login_grants_assigned_scope_and_carries_it_in_jwt(
    app_client: TestClient,
) -> None:
    response = _login(app_client, DAEMON, scope="deliver:local")
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "deliver:local"
    claims = jwt.decode(
        body["access_token"], key=auth.SECRET_KEY, algorithms=[auth.ALGORITHM]
    )
    assert claims["scope"] == "deliver:local"


@pytest.mark.parametrize(
    ("address", "scope"),
    [
        (DAEMON, "deliver:federate"),
        (DAEMON, "unknown:scope"),
        (USER, "deliver:local"),
    ],
)
def test_login_rejects_unavailable_or_invalid_scopes(
    app_client: TestClient, address: str, scope: str
) -> None:
    response = _login(app_client, address, scope=scope)
    assert response.status_code == 400
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_scope"'


def test_local_daemon_endpoints_require_scope_in_token(
    app_client: TestClient,
) -> None:
    unscoped = _login(app_client, DAEMON)
    assert unscoped.status_code == 200
    response = app_client.post(
        "/daemon/message-buffer/clear",
        headers=_bearer(unscoped.json()["access_token"]),
    )
    assert response.status_code == 403
    assert 'scope="deliver:local"' in response.headers["www-authenticate"]


def test_token_grant_cannot_exceed_live_daemon_assignment(
    app_client: TestClient,
) -> None:
    token = auth.create_access_token(data={"sub": DAEMON, "scope": "deliver:federate"})
    draft_id = _create_draft(app_client, token)
    response = app_client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": ["user:bob@remote.example"]},
        headers=_bearer(token),
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("assigned", "granted", "recipient", "expected"),
    [
        (["deliver:local"], "deliver:local", "user:bob@localhost", 200),
        (["deliver:local"], "deliver:local", "user:bob@remote.example", 403),
        (["deliver:federate"], "deliver:federate", "user:bob@remote.example", 200),
        (["deliver:federate"], "deliver:federate", "user:bob@localhost", 403),
        (
            ["deliver:federate:remote.example"],
            "deliver:federate:remote.example",
            "user:bob@remote.example",
            403,
        ),
    ],
)
def test_daemon_send_authorization_matrix(
    app_client: TestClient,
    headers_for,
    assigned: list[str],
    granted: str,
    recipient: str,
    expected: int,
) -> None:
    address, password = _create_daemon(
        app_client,
        headers_for,
        worker_name="scoped-worker",
        scopes=assigned,
    )
    login = _login(app_client, address, password=password, scope=granted)
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    draft_id = _create_draft(app_client, token)
    response = app_client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": [recipient]},
        headers=_bearer(token),
    )
    assert response.status_code == expected, response.text


def test_non_daemon_remote_send_keeps_ordinary_authority(
    app_client: TestClient,
) -> None:
    login = _login(app_client, USER)
    token = login.json()["access_token"]
    draft_id = _create_draft(app_client, token)
    response = app_client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": ["user:bob@remote.example"]},
        headers=_bearer(token),
    )
    assert response.status_code == 200, response.text


def test_any_remote_recipient_selects_federate_scope(
    app_client: TestClient, headers_for
) -> None:
    address, password = _create_daemon(
        app_client,
        headers_for,
        worker_name="mixed-worker",
        scopes=["deliver:local", "deliver:federate"],
    )
    login = _login(app_client, address, password=password, scope="deliver:federate")
    token = login.json()["access_token"]
    draft_id = _create_draft(app_client, token)
    response = app_client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": ["user:bob@localhost", "user:bob@remote.example"]},
        headers=_bearer(token),
    )
    assert response.status_code == 200, response.text
