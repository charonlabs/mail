# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
End-to-end HTTP coverage for the endpoints that are ``NotImplementedError``
stubs on the memory backend but fully implemented on sqlite (the routers were
wired to delegate to the backend). Pinned to the sqlite backend; the memory
backend's stub behavior is asserted in ``test_stubs.py``.
"""

import pytest
from fastapi.testclient import TestClient

USER = "user:alice@localhost"
OTHER_USER = "user:bob@localhost"
DAEMON = "daemon:dummy@localhost"
ADMIN = "admin:ryan@localhost"


@pytest.fixture
def backend_kind() -> str:
    """Pin this suite to sqlite, where these endpoints are implemented."""

    return "sqlite"


def test_delete_inbox_message_moves_to_trash(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, [OTHER_USER])
    bob = headers_for(OTHER_USER)

    response = app_client.delete(f"/inbox/{message_id}", headers=bob)
    assert response.status_code == 200

    # Gone from the inbox, now readable from trash.
    assert app_client.get(f"/inbox/{message_id}", headers=bob).status_code == 404
    assert app_client.get(f"/trash/{message_id}", headers=bob).status_code == 200


def test_delete_draft_removes_it(app_client: TestClient, headers_for) -> None:
    headers = headers_for(USER)
    response = app_client.post(
        "/drafts",
        json={"subject": "Disposable", "body": "Delete me"},
        headers=headers,
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]

    response = app_client.delete(f"/drafts/{draft_id}", headers=headers)
    assert response.status_code == 200
    assert app_client.get(f"/drafts/{draft_id}", headers=headers).status_code == 404


def test_delete_trashed_message_removes_it(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, [OTHER_USER])
    bob = headers_for(OTHER_USER)
    app_client.delete(f"/inbox/{message_id}", headers=bob)  # inbox -> trash

    response = app_client.delete(f"/trash/{message_id}", headers=bob)
    assert response.status_code == 200
    assert app_client.get(f"/trash/{message_id}", headers=bob).status_code == 404


def test_trash_clear_empties_box(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    bob = headers_for(OTHER_USER)
    for _ in range(2):
        message_id = deliver_message(USER, [OTHER_USER])
        app_client.delete(f"/inbox/{message_id}", headers=bob)

    response = app_client.post("/trash/clear", headers=bob)
    assert response.status_code == 200
    assert len(response.json()["entries"]) == 2
    assert app_client.get("/trash", headers=bob).json()["entries"] == []


def test_daemon_deliver_remote_delivers_to_local_inbox(
    app_client: TestClient, headers_for
) -> None:
    message_id = "99999999-9999-4999-8999-999999999999"
    response = app_client.post(
        "/daemon/deliver/remote",
        json={
            "messages": [
                {
                    "mail_version": "2.0",
                    "message_id": message_id,
                    "sender": "echo@otherswarm@remote.example.com",
                    "recipients": [OTHER_USER],
                    "subject": "Remote",
                    "body": "from afar",
                    "tags": [],
                    "sent_at": "2026-06-24T00:00:00Z",
                    "metadata": {},
                }
            ]
        },
        headers=headers_for(DAEMON),
    )
    assert response.status_code == 200
    assert response.json()["messages"][0]["message_id"] == message_id

    opened = app_client.get(f"/inbox/{message_id}", headers=headers_for(OTHER_USER))
    assert opened.status_code == 200
    assert opened.json()["entry"]["message"]["body"] == "from afar"


def test_patch_webhook_updates(app_client: TestClient, headers_for) -> None:
    headers = headers_for(ADMIN)
    response = app_client.post(
        "/admin/webhooks",
        json={
            "url": "https://example.com/mail-events",
            "events": ["mail.delivered"],
            "secret": "shhh",
        },
        headers=headers,
    )
    webhook_id = response.json()["webhook"]["webhook_id"]

    response = app_client.patch(
        f"/admin/webhooks/{webhook_id}",
        json={"url": "https://example.com/elsewhere", "secret": "new-secret"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()["webhook"]
    assert body["webhook_id"] == webhook_id  # id preserved across URL move
    assert body["url"] == "https://example.com/elsewhere"

    # Refetch by id reflects the new URL.
    refetched = app_client.get(f"/admin/webhooks/{webhook_id}", headers=headers)
    assert refetched.json()["webhook"]["url"] == "https://example.com/elsewhere"
