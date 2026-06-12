# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
Filesystem persistence round-trips for every entity type the memory
backend saves on shutdown and loads on startup. Only the lists
collection had round-trip coverage before; these tests pin the rest,
so a serialization change can't silently lose a collection.
"""

from datetime import UTC, datetime
from pathlib import Path

from mail_protocol.core.drafts import MAILDraft, MAILDraftsEntry
from mail_protocol.core.inbox import MAILInboxEntrySummary
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.trash import MAILTrashEntry
from mail_protocol.core.user_agents import (
    MAILUser,
    MAILUserAgentInBackend,
)
from mail_protocol.core.webhooks import MAILWebhook
from mail_server.backends.memory import fs as memory_fs

NOW = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
UUID = "55555555-5555-4555-8555-555555555555"
USER = "user:alice@localhost"
AGENT = "sage@chorus@localhost"


def _message() -> MAILMessage:
    return MAILMessage(
        message_id=UUID,
        sender=USER,
        recipients=[AGENT],
        subject="Persisted",
        body="Survives a save/load cycle.",
        sent_at=NOW,
        metadata={},
    )


async def test_user_agents_roundtrip(deployment_dir: Path) -> None:
    record = {
        USER: MAILUserAgentInBackend(
            user_agent=MAILUser(ua_type="user", user_id="alice", host="localhost"),
            hashed_password="a-stored-hash",
        )
    }
    await memory_fs.save_user_agents(record)
    assert await memory_fs.load_user_agents() == record


async def test_swarms_roundtrip(deployment_dir: Path) -> None:
    record = {
        "chorus": MAILSwarm(
            name="chorus",
            description="A test swarm.",
            keywords=["testing"],
            agents=["sage"],
            metadata={},
        )
    }
    await memory_fs.save_swarms(record)
    assert await memory_fs.load_swarms() == record


async def test_messages_roundtrip(deployment_dir: Path) -> None:
    record = {UUID: _message()}
    await memory_fs.save_messages(record)
    assert await memory_fs.load_messages() == record


async def test_inbox_entries_and_inboxes_roundtrip(deployment_dir: Path) -> None:
    entries = {
        UUID: MAILInboxEntrySummary(
            message_id=UUID,
            sender=USER,
            subject="Persisted",
            body_size=10,
            received_at=NOW,
            delivered_by="daemon:dummy@localhost",
        )
    }
    boxes = {AGENT: [UUID], USER: []}
    await memory_fs.save_inbox_entries(entries)
    await memory_fs.save_inboxes(boxes)
    assert await memory_fs.load_inbox_entries() == entries
    assert await memory_fs.load_inboxes() == boxes


async def test_outbox_entries_and_outboxes_roundtrip(deployment_dir: Path) -> None:
    entries = {
        UUID: MAILOutboxEntrySummary(
            message_id=UUID,
            recipients=[AGENT],
            subject="Persisted",
            body_size=10,
            sent_at=NOW,
            delivered_at=NOW,
            delivered_by="daemon:dummy@localhost",
        )
    }
    boxes = {USER: [UUID]}
    await memory_fs.save_outbox_entries(entries)
    await memory_fs.save_outboxes(boxes)
    assert await memory_fs.load_outbox_entries() == entries
    assert await memory_fs.load_outboxes() == boxes


async def test_draft_entries_and_drafts_roundtrip(deployment_dir: Path) -> None:
    entries = {
        UUID: MAILDraftsEntry(
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
    }
    boxes = {USER: [UUID]}
    await memory_fs.save_draft_entries(entries)
    await memory_fs.save_drafts(boxes)
    assert await memory_fs.load_draft_entries() == entries
    assert await memory_fs.load_drafts() == boxes


async def test_trash_entries_and_trashes_roundtrip(deployment_dir: Path) -> None:
    entries = {UUID: MAILTrashEntry(message=_message(), trashed_at=NOW)}
    boxes = {USER: [UUID]}
    await memory_fs.save_trash_entries(entries)
    await memory_fs.save_trashes(boxes)
    assert await memory_fs.load_trash_entries() == entries
    assert await memory_fs.load_trashes() == boxes


async def test_message_buffer_roundtrip(deployment_dir: Path) -> None:
    buffer = [UUID, "66666666-6666-4666-8666-666666666666"]
    await memory_fs.save_message_buffer(buffer)
    assert await memory_fs.load_message_buffer() == buffer


async def test_webhooks_roundtrip(deployment_dir: Path) -> None:
    record = {
        "https://hooks.example.com/mail": MAILWebhook(
            webhook_id=f"wh_{UUID}",
            url="https://hooks.example.com/mail",
            events=["mail.delivered"],
            secret="shhh",
        )
    }
    await memory_fs.save_webhooks(record)
    assert await memory_fs.load_webhooks() == record


async def test_empty_deployment_loads_empty_collections(
    deployment_dir: Path,
) -> None:
    """A freshly provisioned deployment dir yields empty state."""

    assert await memory_fs.load_user_agents() == {}
    assert await memory_fs.load_messages() == {}
    assert await memory_fs.load_inboxes() == {}
    assert await memory_fs.load_message_buffer() == []
    assert await memory_fs.load_webhooks() == {}
