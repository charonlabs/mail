# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from fastapi.testclient import TestClient

USER = "user:alice@localhost"
OTHER_USER = "user:bob@localhost"
DAEMON = "daemon:dummy@localhost"


def _compose_and_send(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/drafts",
        json={"subject": "Buffered", "body": "Awaiting delivery"},
        headers=headers,
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]
    response = client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": [OTHER_USER]},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["message"]["message_id"]


def test_clear_message_buffer_returns_pending_ids_once(
    app_client: TestClient, headers_for
) -> None:
    message_id = _compose_and_send(app_client, headers_for(USER))
    daemon_headers = headers_for(DAEMON)

    response = app_client.post("/daemon/message-buffer/clear", headers=daemon_headers)
    assert response.status_code == 200
    assert response.json()["message_ids"] == [message_id]

    # The buffer is drained; a second clear returns nothing.
    response = app_client.post("/daemon/message-buffer/clear", headers=daemon_headers)
    assert response.status_code == 200
    assert response.json()["message_ids"] == []


def test_deliver_local_updates_recipient_inbox(
    app_client: TestClient, headers_for
) -> None:
    message_id = _compose_and_send(app_client, headers_for(USER))
    daemon_headers = headers_for(DAEMON)
    app_client.post("/daemon/message-buffer/clear", headers=daemon_headers)

    response = app_client.post(
        "/daemon/deliver/local",
        json={"message_ids": [message_id]},
        headers=daemon_headers,
    )
    assert response.status_code == 200
    summaries = response.json()["messages"]
    assert len(summaries) == 1
    assert summaries[0]["message_id"] == message_id

    # The recipient can now open it from their inbox...
    opened = app_client.get(
        f"/inbox/{message_id}", headers=headers_for(OTHER_USER)
    )
    assert opened.status_code == 200
    # ...and the sender's outbox entry is marked delivered.
    outbox = app_client.get(f"/outbox/{message_id}", headers=headers_for(USER))
    assert outbox.status_code == 200
    assert outbox.json()["entry"]["delivered_at"] is not None


def test_deliver_local_skips_unknown_message_ids(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/daemon/deliver/local",
        json={"message_ids": ["11111111-1111-4111-8111-111111111111"]},
        headers=headers_for(DAEMON),
    )
    assert response.status_code == 200
    assert response.json()["messages"] == []


def test_deliver_local_rejects_non_uuid_ids(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/daemon/deliver/local",
        json={"message_ids": ["not-a-uuid"]},
        headers=headers_for(DAEMON),
    )
    assert response.status_code == 422


def test_deliver_local_skips_unknown_recipient(
    app_client: TestClient, headers_for
) -> None:
    """
    A recipient address that doesn't resolve to a registered user-agent
    is logged and skipped; delivery succeeds for everyone else.
    """

    user_headers = headers_for(USER)
    response = app_client.post(
        "/drafts",
        json={"subject": "Mixed", "body": "One good, one ghost"},
        headers=user_headers,
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]
    response = app_client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": ["user:ghost@localhost", OTHER_USER]},
        headers=user_headers,
    )
    message_id = response.json()["message"]["message_id"]

    daemon_headers = headers_for(DAEMON)
    app_client.post("/daemon/message-buffer/clear", headers=daemon_headers)
    response = app_client.post(
        "/daemon/deliver/local",
        json={"message_ids": [message_id]},
        headers=daemon_headers,
    )
    assert response.status_code == 200
    # The known recipient received it; the unknown one was skipped without error.
    opened = app_client.get(
        f"/inbox/{message_id}", headers=headers_for(OTHER_USER)
    )
    assert opened.status_code == 200
