# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.trash import MAILTrashEntry
from mail_server.backends.memory.api import MemoryBackend

USER = "user:alice@localhost"
OTHER_USER = "user:bob@localhost"


# ─── Inbox ─────────────────────────────────────────────────────────


def test_inbox_starts_empty(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/inbox/", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_inbox_lists_delivered_message(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, [OTHER_USER], subject="Greetings")
    response = app_client.get("/inbox/", headers=headers_for(OTHER_USER))
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["message_id"] == message_id
    assert entries[0]["sender"] == USER
    assert entries[0]["subject"] == "Greetings"


def test_inbox_open_returns_full_message(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, [OTHER_USER], body="The full body")
    response = app_client.get(
        f"/inbox/{message_id}", headers=headers_for(OTHER_USER)
    )
    assert response.status_code == 200
    entry = response.json()["entry"]
    assert entry["message"]["body"] == "The full body"
    assert entry["message"]["sender"] == USER


def test_inbox_open_unknown_id_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get(
        "/inbox/11111111-1111-4111-8111-111111111111",
        headers=headers_for(USER),
    )
    assert response.status_code == 404


def test_inbox_open_isolated_between_users(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    """A message delivered to bob must not be readable from alice's inbox."""

    message_id = deliver_message(USER, [OTHER_USER])
    response = app_client.get(f"/inbox/{message_id}", headers=headers_for(USER))
    assert response.status_code == 404


# ─── Outbox ────────────────────────────────────────────────────────


def test_outbox_starts_empty(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/outbox/", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_outbox_entry_created_on_send_and_updated_on_delivery(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, [OTHER_USER])
    response = app_client.get("/outbox/", headers=headers_for(USER))
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["message_id"] == message_id
    assert entries[0]["delivered_at"] is not None
    assert entries[0]["delivered_by"] == "daemon:dummy@localhost"


def test_outbox_open_returns_full_message(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, [OTHER_USER], body="Sent body")
    response = app_client.get(
        f"/outbox/{message_id}", headers=headers_for(USER)
    )
    assert response.status_code == 200
    assert response.json()["entry"]["message"]["body"] == "Sent body"


def test_outbox_open_unknown_id_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get(
        "/outbox/11111111-1111-4111-8111-111111111111",
        headers=headers_for(USER),
    )
    assert response.status_code == 404


def test_outbox_isolated_between_users(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, [OTHER_USER])
    response = app_client.get(
        f"/outbox/{message_id}", headers=headers_for(OTHER_USER)
    )
    assert response.status_code == 404


# ─── Drafts ────────────────────────────────────────────────────────


def test_drafts_start_empty(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/drafts/", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_post_draft_creates_entry(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/drafts/",
        json={"subject": "A subject", "body": "A body"},
        headers=headers_for(USER),
    )
    assert response.status_code == 200
    draft = response.json()["entry"]["draft"]
    assert draft["subject"] == "A subject"
    assert draft["body"] == "A body"
    assert draft["draft_id"]

    response = app_client.get(
        f"/drafts/{draft['draft_id']}", headers=headers_for(USER)
    )
    assert response.status_code == 200


def test_post_draft_rejects_missing_field(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts/", json={"subject": "no body"}, headers=headers_for(USER)
    )
    assert response.status_code == 422


def test_post_draft_rejects_overlong_subject(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts/",
        json={"subject": "s" * 256, "body": "A body"},
        headers=headers_for(USER),
    )
    assert response.status_code == 422


def test_post_draft_rejects_empty_subject(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts/",
        json={"subject": "", "body": "A body"},
        headers=headers_for(USER),
    )
    assert response.status_code == 422


def test_post_draft_rejects_unparseable_body(
    app_client: TestClient, headers_for
) -> None:
    """An unparseable JSON body must 422 like an invalid one (not 500)."""

    response = app_client.post(
        "/drafts/",
        content=b"not json",
        headers={**headers_for(USER), "Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_get_draft_unknown_id_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get(
        "/drafts/11111111-1111-4111-8111-111111111111",
        headers=headers_for(USER),
    )
    assert response.status_code == 404


def test_drafts_isolated_between_users(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts/",
        json={"subject": "Private", "body": "Draft"},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]
    response = app_client.get(
        f"/drafts/{draft_id}", headers=headers_for(OTHER_USER)
    )
    assert response.status_code == 404


def test_send_draft_creates_message_and_buffers_it(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    response = app_client.post(
        "/drafts/",
        json={"subject": "Outgoing", "body": "Payload"},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]

    response = app_client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": [OTHER_USER]},
        headers=headers_for(USER),
    )
    assert response.status_code == 200
    message = response.json()["message"]
    assert message["sender"] == USER
    assert message["recipients"] == [OTHER_USER]
    assert message["subject"] == "Outgoing"
    assert message["message_id"] != draft_id
    assert message["message_id"] in backend.message_buffer


def test_send_draft_rejects_invalid_recipients(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts/",
        json={"subject": "Outgoing", "body": "Payload"},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]

    response = app_client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": ["not-an-address"]},
        headers=headers_for(USER),
    )
    assert response.status_code == 422


def test_send_unknown_draft_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts/11111111-1111-4111-8111-111111111111/send",
        json={"recipients": [OTHER_USER]},
        headers=headers_for(USER),
    )
    assert response.status_code == 404


# ─── Trash ─────────────────────────────────────────────────────────


def _seed_trash(backend: MemoryBackend, owner: str) -> str:
    message = MAILMessage(
        message_id="22222222-2222-4222-8222-222222222222",
        sender="sage@chorus@localhost",
        recipients=[owner],
        subject="Trashed",
        body="This message was moved to trash.",
        sent_at=datetime(2026, 6, 11, tzinfo=UTC),
        metadata={},
    )
    backend.trash_entries[message.message_id] = MAILTrashEntry(
        message=message,
        trashed_at=datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
    )
    backend.trashes[owner].append(message.message_id)
    return message.message_id


def test_trash_starts_empty(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/trash/", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_trash_lists_seeded_entry(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    message_id = _seed_trash(backend, USER)
    response = app_client.get("/trash/", headers=headers_for(USER))
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["message_id"] == message_id


def test_trash_open_returns_entry(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    message_id = _seed_trash(backend, USER)
    response = app_client.get(
        f"/trash/{message_id}", headers=headers_for(USER)
    )
    assert response.status_code == 200
    assert response.json()["entry"]["message"]["subject"] == "Trashed"


def test_trash_open_unknown_id_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get(
        "/trash/11111111-1111-4111-8111-111111111111",
        headers=headers_for(USER),
    )
    assert response.status_code == 404


def test_trash_isolated_between_users(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    message_id = _seed_trash(backend, USER)
    response = app_client.get(
        f"/trash/{message_id}", headers=headers_for(OTHER_USER)
    )
    assert response.status_code == 404
