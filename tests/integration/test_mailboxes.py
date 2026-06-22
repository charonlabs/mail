# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from mail_protocol.core.constants import MESSAGE_SUBJECT_LEN_MAX
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.trash import MAILTrashEntry
from mail_server.backends.memory.api import MemoryBackend

USER = "user:alice@localhost"
OTHER_USER = "user:bob@localhost"


# ─── Inbox ─────────────────────────────────────────────────────────


def test_inbox_starts_empty(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/inbox", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_inbox_lists_delivered_message(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, [OTHER_USER], subject="Greetings")
    response = app_client.get("/inbox", headers=headers_for(OTHER_USER))
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
    response = app_client.get(f"/inbox/{message_id}", headers=headers_for(OTHER_USER))
    assert response.status_code == 200
    entry = response.json()["entry"]
    assert entry["message"]["body"] == "The full body"
    assert entry["message"]["sender"] == USER


def test_inbox_open_unknown_id_returns_404(app_client: TestClient, headers_for) -> None:
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
    response = app_client.get("/outbox", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_outbox_entry_created_on_send_and_updated_on_delivery(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, [OTHER_USER])
    response = app_client.get("/outbox", headers=headers_for(USER))
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
    response = app_client.get(f"/outbox/{message_id}", headers=headers_for(USER))
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
    response = app_client.get(f"/outbox/{message_id}", headers=headers_for(OTHER_USER))
    assert response.status_code == 404


# ─── Drafts ────────────────────────────────────────────────────────


def test_drafts_start_empty(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/drafts", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_post_draft_creates_entry(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "A subject", "body": "A body"},
        headers=headers_for(USER),
    )
    assert response.status_code == 200
    draft = response.json()["entry"]["draft"]
    assert draft["subject"] == "A subject"
    assert draft["body"] == "A body"
    assert draft["draft_id"]

    response = app_client.get(f"/drafts/{draft['draft_id']}", headers=headers_for(USER))
    assert response.status_code == 200


def test_post_draft_rejects_missing_field(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/drafts", json={"subject": "no body"}, headers=headers_for(USER)
    )
    assert response.status_code == 422


def test_post_draft_rejects_overlong_subject(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "s" * (MESSAGE_SUBJECT_LEN_MAX + 1), "body": "A body"},
        headers=headers_for(USER),
    )
    assert response.status_code == 422


def test_post_draft_rejects_empty_subject(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "", "body": "A body"},
        headers=headers_for(USER),
    )
    assert response.status_code == 422


def test_post_draft_rejects_unparseable_body(
    app_client: TestClient, headers_for
) -> None:
    """An unparseable JSON body must 422 like an invalid one (not 500)."""

    response = app_client.post(
        "/drafts",
        content=b"not json",
        headers={**headers_for(USER), "Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_get_draft_unknown_id_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.get(
        "/drafts/11111111-1111-4111-8111-111111111111",
        headers=headers_for(USER),
    )
    assert response.status_code == 404


def test_drafts_isolated_between_users(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "Private", "body": "Draft"},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]
    response = app_client.get(f"/drafts/{draft_id}", headers=headers_for(OTHER_USER))
    assert response.status_code == 404


def test_send_draft_creates_message_and_buffers_it(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    response = app_client.post(
        "/drafts",
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


def test_send_draft_rejects_empty_recipients(
    app_client: TestClient, headers_for
) -> None:
    """SPEC.md §7.3: recipients MUST contain at least 1 entry."""

    response = app_client.post(
        "/drafts",
        json={"subject": "Outgoing", "body": "Payload"},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]

    response = app_client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": []},
        headers=headers_for(USER),
    )
    assert response.status_code == 422


def test_send_draft_rejects_invalid_recipients(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts",
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


def test_send_unknown_draft_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/drafts/11111111-1111-4111-8111-111111111111/send",
        json={"recipients": [OTHER_USER]},
        headers=headers_for(USER),
    )
    assert response.status_code == 404


def test_patch_draft_updates_fields(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "Original", "body": "Original body", "tags": ["a"]},
        headers=headers_for(USER),
    )
    draft = response.json()["entry"]["draft"]
    draft_id = draft["draft_id"]
    assert draft["updated_at"] is None

    response = app_client.patch(
        f"/drafts/{draft_id}",
        json={"subject": "Updated", "body": "Updated body", "tags": ["b", "c"]},
        headers=headers_for(USER),
    )
    assert response.status_code == 200
    updated = response.json()["entry"]["draft"]
    assert updated["subject"] == "Updated"
    assert updated["body"] == "Updated body"
    assert updated["tags"] == ["b", "c"]
    assert updated["updated_at"] is not None
    # the change is persisted, not just echoed back
    response = app_client.get(f"/drafts/{draft_id}", headers=headers_for(USER))
    assert response.json()["entry"]["draft"]["subject"] == "Updated"


def test_patch_draft_partial_leaves_other_fields(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "Keep subject", "body": "Old body", "tags": ["x"]},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]

    response = app_client.patch(
        f"/drafts/{draft_id}",
        json={"body": "New body"},
        headers=headers_for(USER),
    )
    assert response.status_code == 200
    updated = response.json()["entry"]["draft"]
    assert updated["body"] == "New body"
    assert updated["subject"] == "Keep subject"
    assert updated["tags"] == ["x"]


def test_patch_draft_empty_tags_clears_them(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "Subject", "body": "Body", "tags": ["x", "y"]},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]

    response = app_client.patch(
        f"/drafts/{draft_id}",
        json={"tags": []},
        headers=headers_for(USER),
    )
    assert response.status_code == 200
    assert response.json()["entry"]["draft"]["tags"] == []


def test_patch_draft_rejects_overlong_subject(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "Subject", "body": "Body"},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]

    response = app_client.patch(
        f"/drafts/{draft_id}",
        json={"subject": "x" * (MESSAGE_SUBJECT_LEN_MAX + 1)},
        headers=headers_for(USER),
    )
    assert response.status_code == 422


def test_patch_draft_unknown_id_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.patch(
        "/drafts/11111111-1111-4111-8111-111111111111",
        json={"subject": "Updated"},
        headers=headers_for(USER),
    )
    assert response.status_code == 404


def test_patch_draft_isolated_between_users(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "Private", "body": "Draft"},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]

    response = app_client.patch(
        f"/drafts/{draft_id}",
        json={"subject": "Hijacked"},
        headers=headers_for(OTHER_USER),
    )
    assert response.status_code == 404


def test_patch_draft_then_send_uses_new_content(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/drafts",
        json={"subject": "Original", "body": "Original body"},
        headers=headers_for(USER),
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]

    app_client.patch(
        f"/drafts/{draft_id}",
        json={"subject": "Edited", "body": "Edited body"},
        headers=headers_for(USER),
    )

    response = app_client.post(
        f"/drafts/{draft_id}/send",
        json={"recipients": [OTHER_USER]},
        headers=headers_for(USER),
    )
    assert response.status_code == 200
    message = response.json()["message"]
    assert message["subject"] == "Edited"
    assert message["body"] == "Edited body"


# ─── Trash ─────────────────────────────────────────────────────────


def _seed_trash(backend: MemoryBackend, owner: str) -> str:
    message = MAILMessage(
        mail_version="2.0",
        message_id="22222222-2222-4222-8222-222222222222",
        sender="sage@chorus@localhost",
        recipients=[owner],
        subject="Trashed",
        body="This message was moved to trash.",
        tags=[],
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
    response = app_client.get("/trash", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_trash_lists_seeded_entry(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    message_id = _seed_trash(backend, USER)
    response = app_client.get("/trash", headers=headers_for(USER))
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["message_id"] == message_id


def test_trash_open_returns_entry(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    message_id = _seed_trash(backend, USER)
    response = app_client.get(f"/trash/{message_id}", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["entry"]["message"]["subject"] == "Trashed"


def test_trash_open_unknown_id_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.get(
        "/trash/11111111-1111-4111-8111-111111111111",
        headers=headers_for(USER),
    )
    assert response.status_code == 404


def test_trash_isolated_between_users(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    message_id = _seed_trash(backend, USER)
    response = app_client.get(f"/trash/{message_id}", headers=headers_for(OTHER_USER))
    assert response.status_code == 404


# ─── Box query parameters ──────────────────────────────────────────


def _seed_trash_n(backend: MemoryBackend, owner: str, n: int) -> list[str]:
    """
    Seed ``n`` trash entries for ``owner``. ``trashed_at`` *increases* with
    insertion order while the underlying message's ``sent_at`` *decreases*, so
    sorting by ``entered_at`` (trashed_at) and by ``sent_at`` produce opposite
    orders — letting a single seed exercise both. Returns the message IDs in
    insertion order (oldest-trashed first), so ``ids[-1]`` is the newest.

    The message is also registered in ``backend.messages`` because the
    ``sent_at`` sort resolves send time via that store (as the real local
    delivery path populates it).
    """

    ids: list[str] = []
    for i in range(n):
        message_id = f"{i:08d}-2222-4222-8222-222222222222"
        message = MAILMessage(
            mail_version="2.0",
            message_id=message_id,
            sender="sage@chorus@localhost",
            recipients=[owner],
            subject=f"Trashed {i}",
            body="body",
            tags=[],
            sent_at=datetime(2026, 6, 1, 12, n - i, tzinfo=UTC),  # decreasing
            metadata={},
        )
        backend.messages[message_id] = message
        backend.trash_entries[message_id] = MAILTrashEntry(
            message=message,
            trashed_at=datetime(2026, 6, 11, 12, i, tzinfo=UTC),  # increasing
        )
        backend.trashes[owner].append(message_id)
        ids.append(message_id)
    return ids


def test_box_metadata_reports_pagination_defaults(
    app_client: TestClient, headers_for
) -> None:
    """An empty box still echoes the applied (default) filters."""

    response = app_client.get("/inbox", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["metadata"] == {
        "total": 0,
        "returned": 0,
        "limit": 20,
        "offset": 0,
        "sort_by": "entered_at",
        "order": "desc",
    }


def test_box_rejects_unknown_query_param(app_client: TestClient, headers_for) -> None:
    """`extra="forbid"` makes an unknown query param a 422."""

    response = app_client.get("/inbox?bogus=1", headers=headers_for(USER))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=abc",
        "offset=-1",
        "sort_by=bogus",
        "order=sideways",
    ],
)
def test_box_rejects_invalid_query_params(
    app_client: TestClient, headers_for, query: str
) -> None:
    response = app_client.get(f"/inbox?{query}", headers=headers_for(USER))
    assert response.status_code == 422


def test_box_pagination_slices_and_counts(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    ids = _seed_trash_n(backend, USER, 5)  # oldest → newest

    response = app_client.get("/trash?limit=2&offset=0", headers=headers_for(USER))
    assert response.status_code == 200
    body = response.json()
    # default sort is entered_at (trashed_at) descending → newest first
    assert [e["message_id"] for e in body["entries"]] == [ids[4], ids[3]]
    assert body["metadata"]["total"] == 5
    assert body["metadata"]["returned"] == 2

    response = app_client.get("/trash?limit=2&offset=2", headers=headers_for(USER))
    assert [e["message_id"] for e in response.json()["entries"]] == [ids[2], ids[1]]


def test_box_sort_order_ascending(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    ids = _seed_trash_n(backend, USER, 3)

    response = app_client.get("/trash?order=asc", headers=headers_for(USER))
    assert response.status_code == 200
    assert [e["message_id"] for e in response.json()["entries"]] == ids


def test_box_offset_past_end_returns_empty_page(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    _seed_trash_n(backend, USER, 3)

    response = app_client.get("/trash?offset=10", headers=headers_for(USER))
    assert response.status_code == 200
    body = response.json()
    assert body["entries"] == []
    assert body["metadata"]["total"] == 3
    assert body["metadata"]["returned"] == 0


def test_box_sort_by_sent_at_uses_message_send_time(
    app_client: TestClient, headers_for, backend: MemoryBackend
) -> None:
    """
    `sort_by=sent_at` orders by the underlying message's send time, which the
    seed makes the exact reverse of the default `entered_at` (trashed_at) order.
    """

    ids = _seed_trash_n(backend, USER, 3)

    default = app_client.get("/trash", headers=headers_for(USER))
    assert [e["message_id"] for e in default.json()["entries"]] == [
        ids[2],
        ids[1],
        ids[0],
    ]

    by_sent = app_client.get("/trash?sort_by=sent_at", headers=headers_for(USER))
    assert by_sent.status_code == 200
    assert [e["message_id"] for e in by_sent.json()["entries"]] == [
        ids[0],
        ids[1],
        ids[2],
    ]


def test_drafts_reject_sort_by_sent_at(app_client: TestClient, headers_for) -> None:
    """Drafts have no send time, so `sort_by=sent_at` must 422 (not silently fall back)."""

    response = app_client.get("/drafts?sort_by=sent_at", headers=headers_for(USER))
    assert response.status_code == 422
    # other boxes still accept it
    assert (
        app_client.get("/inbox?sort_by=sent_at", headers=headers_for(USER)).status_code
        == 200
    )
