# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Round-trips for every model-bearing SQLite row serializer:
``model -> to_columns -> Row(**columns) -> from_row`` must be identity.

This pins the hybrid invariant — ``from_row`` rehydrates solely from the
``body`` JSON column, so a serialization change can't silently corrupt a
collection. The two body-less tables (``mailbox_items``, ``message_buffer``)
have no serializer and are covered by repository tests instead.

The typed columns are asserted separately, since those (not ``body``) are what
``WHERE`` / ``ORDER BY`` rely on.
"""

from datetime import UTC, datetime

from mail_protocol.core.drafts import MAILDraft, MAILDraftsEntry
from mail_protocol.core.inbox import MAILInboxEntrySummary
from mail_protocol.core.lists import MAILList, MAILListInBackend
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.trash import MAILTrashEntry
from mail_protocol.core.user_agents import (
    MAILAgent,
    MAILUser,
    MAILUserAgentInBackend,
)
from mail_protocol.core.webhooks import MAILWebhook
from mail_server.backends.sqlite import serializers as s
from mail_server.backends.sqlite.schema import (
    DraftEntryRow,
    InboxEntryRow,
    ListRow,
    MessageRow,
    OutboxEntryRow,
    SwarmRow,
    TrashEntryRow,
    UserAgentRow,
    WebhookRow,
)

NOW = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
UUID = "55555555-5555-4555-8555-555555555555"
USER = "user:alice@localhost"
AGENT = "sage@chorus@localhost"
DAEMON = "daemon:dummy@localhost"


def _message() -> MAILMessage:
    return MAILMessage(
        mail_version="2.0",
        message_id=UUID,
        sender=USER,
        recipients=[AGENT],
        subject="Persisted",
        body="Survives a round-trip.",
        tags=[],
        sent_at=NOW,
        metadata={},
    )


def test_user_agent_roundtrip() -> None:
    model = MAILUserAgentInBackend(
        user_agent=MAILUser(ua_type="user", user_id="alice", host="localhost"),
        hashed_password="a-stored-hash",
    )
    cols = s.user_agent_to_columns(model)
    assert cols["address"] == USER
    assert cols["ua_type"] == "user"
    assert cols["swarm"] is None
    assert cols["host"] == "localhost"
    assert cols["hashed_password"] == "a-stored-hash"
    assert s.user_agent_from_row(UserAgentRow(**cols)) == model


def test_user_agent_agent_carries_swarm_column() -> None:
    model = MAILUserAgentInBackend(
        user_agent=MAILAgent(
            ua_type="agent", name="sage", swarm="chorus", host="localhost"
        ),
        hashed_password="hash",
    )
    cols = s.user_agent_to_columns(model)
    assert cols["address"] == AGENT
    assert cols["swarm"] == "chorus"
    assert s.user_agent_from_row(UserAgentRow(**cols)) == model


def test_swarm_roundtrip() -> None:
    model = MAILSwarm(
        name="chorus",
        description="A test swarm.",
        keywords=["testing"],
        agents=["sage"],
        metadata={},
    )
    cols = s.swarm_to_columns(model)
    assert cols["name"] == "chorus"
    assert s.swarm_from_row(SwarmRow(**cols)) == model


def test_message_roundtrip() -> None:
    model = _message()
    cols = s.message_to_columns(model)
    assert cols["message_id"] == UUID
    assert cols["sender"] == USER
    assert cols["subject"] == "Persisted"
    assert cols["reply_to"] is None
    assert cols["sent_at"] == NOW
    assert s.message_from_row(MessageRow(**cols)) == model


def test_inbox_entry_roundtrip() -> None:
    model = MAILInboxEntrySummary(
        message_id=UUID,
        sender=USER,
        subject="Persisted",
        body_size=10,
        received_at=NOW,
        delivered_by=DAEMON,
    )
    cols = s.inbox_entry_to_columns(model)
    assert cols["message_id"] == UUID
    assert cols["body_size"] == 10
    assert cols["received_at"] == NOW
    assert cols["delivered_by"] == DAEMON
    assert s.inbox_entry_from_row(InboxEntryRow(**cols)) == model


def test_outbox_entry_roundtrip() -> None:
    model = MAILOutboxEntrySummary(
        message_id=UUID,
        recipients=[AGENT],
        subject="Persisted",
        body_size=10,
        sent_at=NOW,
        delivered_at=NOW,
        delivered_by=DAEMON,
    )
    cols = s.outbox_entry_to_columns(model)
    assert cols["message_id"] == UUID
    assert cols["sent_at"] == NOW
    assert cols["delivered_at"] == NOW
    assert cols["delivered_by"] == DAEMON
    assert s.outbox_entry_from_row(OutboxEntryRow(**cols)) == model


def test_outbox_entry_undelivered_roundtrip() -> None:
    model = MAILOutboxEntrySummary(
        message_id=UUID,
        recipients=[AGENT],
        subject="Persisted",
        body_size=10,
        sent_at=NOW,
    )
    cols = s.outbox_entry_to_columns(model)
    assert cols["delivered_at"] is None
    assert cols["delivered_by"] is None
    assert s.outbox_entry_from_row(OutboxEntryRow(**cols)) == model


def test_draft_entry_roundtrip() -> None:
    model = MAILDraftsEntry(
        draft=MAILDraft(
            draft_id=UUID,
            subject="Persisted",
            body="A draft body.",
            created_at=NOW,
            updated_at=None,
        ),
        sent_at=None,
        sent_by=None,
    )
    cols = s.draft_entry_to_columns(model)
    assert cols["draft_id"] == UUID
    assert cols["created_at"] == NOW
    assert cols["updated_at"] is None
    assert s.draft_entry_from_row(DraftEntryRow(**cols)) == model


def test_trash_entry_roundtrip() -> None:
    model = MAILTrashEntry(message=_message(), trashed_at=NOW)
    cols = s.trash_entry_to_columns(model)
    assert cols["message_id"] == UUID
    assert cols["trashed_at"] == NOW
    assert s.trash_entry_from_row(TrashEntryRow(**cols)) == model


def test_webhook_roundtrip() -> None:
    model = MAILWebhook(
        webhook_id=f"wh_{UUID}",
        url="https://hooks.example.com/mail",
        events=["mail.delivered"],
        secret="shhh",
    )
    cols = s.webhook_to_columns(model)
    assert cols["url"] == "https://hooks.example.com/mail"
    assert cols["webhook_id"] == f"wh_{UUID}"
    assert s.webhook_from_row(WebhookRow(**cols)) == model


def test_list_roundtrip() -> None:
    model = MAILListInBackend(
        **MAILList(
            name="team",
            swarm="chorus",
            host="localhost",
            owner=USER,
            members=[AGENT],
        ).model_dump(),
        list_id=UUID,
        created_at=NOW,
        updated_at=NOW,
    )
    cols = s.list_to_columns(model)
    assert cols["address"] == "list:team@chorus@localhost"
    assert cols["list_id"] == UUID
    assert cols["swarm"] == "chorus"
    assert cols["host"] == "localhost"
    assert cols["created_at"] == NOW
    assert cols["updated_at"] == NOW
    assert s.list_from_row(ListRow(**cols)) == model
