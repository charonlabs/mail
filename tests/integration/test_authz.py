# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
Authorization boundaries: role-restricted routers must reject tokens of
every other role. Wrong-role requests return 401 (not 403) — see
mail_server.auth.validate_admin / validate_daemon.
"""

import pytest
from fastapi.testclient import TestClient

ADMIN = "admin:ryan@localhost"
USER = "user:alice@localhost"
AGENT = "sage@chorus@localhost"
DAEMON = "daemon:dummy@localhost"

ADMIN_ONLY_REQUESTS = [
    ("GET", "/admin/agents", None),
    ("POST", "/admin/agents", {"agent_name": "x", "swarm_name": "chorus", "agent_password": "pw"}),
    ("GET", "/admin/daemons", None),
    ("GET", "/admin/users", None),
    ("POST", "/admin/swarms", {"name": "x", "description": "d", "keywords": []}),
    ("GET", "/admin/webhooks", None),
    ("GET", "/admin/lists", None),
]

DAEMON_ONLY_REQUESTS = [
    ("POST", "/daemon/message-buffer/clear", None),
    ("POST", "/daemon/deliver/local", {"message_ids": []}),
]


def _request(client: TestClient, method: str, path: str, body, headers):
    return client.request(method, path, json=body, headers=headers)


@pytest.mark.parametrize("role", [USER, AGENT, DAEMON])
@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ONLY_REQUESTS)
def test_admin_endpoints_reject_non_admin_roles(
    app_client: TestClient,
    headers_for,
    role: str,
    method: str,
    path: str,
    body,
) -> None:
    response = _request(app_client, method, path, body, headers_for(role))
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ONLY_REQUESTS)
def test_admin_endpoints_reject_missing_token(
    app_client: TestClient,
    method: str,
    path: str,
    body,
) -> None:
    response = _request(app_client, method, path, body, None)
    assert response.status_code == 401


@pytest.mark.parametrize("role", [USER, AGENT, ADMIN])
@pytest.mark.parametrize(("method", "path", "body"), DAEMON_ONLY_REQUESTS)
def test_daemon_endpoints_reject_non_daemon_roles(
    app_client: TestClient,
    headers_for,
    role: str,
    method: str,
    path: str,
    body,
) -> None:
    response = _request(app_client, method, path, body, headers_for(role))
    assert response.status_code == 401


def test_admin_endpoints_accept_admin(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/admin/agents", headers=headers_for(ADMIN))
    assert response.status_code == 200


def test_daemon_endpoints_accept_daemon(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/daemon/message-buffer/clear", headers=headers_for(DAEMON)
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "path", ["/inbox/", "/outbox/", "/drafts/", "/trash/", "/lists"]
)
def test_mailbox_and_list_endpoints_reject_missing_token(
    app_client: TestClient, path: str
) -> None:
    response = app_client.get(path)
    assert response.status_code == 401
