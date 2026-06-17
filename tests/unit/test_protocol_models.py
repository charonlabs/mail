# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
summarize() contracts for every mail_protocol model that has one:
the summary must mirror the source fields and derive body_size/
num_agents rather than carrying the full payload.
"""

from datetime import UTC, datetime

from mail_protocol.core.drafts import MAILDraft, MAILDraftsEntry
from mail_protocol.core.inbox import MAILInboxEntry
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntry
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.trash import MAILTrashEntry

NOW = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
UUID = "55555555-5555-4555-8555-555555555555"


def _message() -> MAILMessage:
    return MAILMessage(
        mail_version="2.0",
        message_id=UUID,
        sender="user:alice@localhost",
        recipients=["sage@chorus@localhost"],
        subject="Hello",
        body="A body worth summarizing.",
        tags=[],
        sent_at=NOW,
        metadata={"k": "v"},
    )


def test_message_summary_derives_body_size() -> None:
    summary = _message().summarize()
    assert summary.message_id == UUID
    assert summary.sender == "user:alice@localhost"
    assert summary.recipients == ["sage@chorus@localhost"]
    assert summary.subject == "Hello"
    assert summary.body_size == len("A body worth summarizing.")
    assert summary.sent_at == NOW


def test_inbox_entry_summary() -> None:
    entry = MAILInboxEntry(
        message=_message(),
        received_at=NOW,
        delivered_by="daemon:dummy@localhost",
    )
    summary = entry.summarize()
    assert summary.message_id == UUID
    assert summary.sender == "user:alice@localhost"
    assert summary.subject == "Hello"
    assert summary.body_size == len(entry.message.body)
    assert summary.received_at == NOW
    assert summary.delivered_by == "daemon:dummy@localhost"


def test_outbox_entry_summary() -> None:
    entry = MAILOutboxEntry(message=_message(), delivered_at=None)
    summary = entry.summarize()
    assert summary.message_id == UUID
    assert summary.recipients == ["sage@chorus@localhost"]
    assert summary.body_size == len(entry.message.body)
    assert summary.delivered_at is None


def test_trash_entry_summary() -> None:
    entry = MAILTrashEntry(message=_message(), trashed_at=NOW)
    summary = entry.summarize()
    assert summary.message_id == UUID
    assert summary.subject == "Hello"
    assert summary.body_size == len(entry.message.body)
    assert summary.trashed_at == NOW


def test_drafts_entry_summary() -> None:
    entry = MAILDraftsEntry(
        draft=MAILDraft(
            draft_id=UUID,
            subject="Hello",
            body="A draft body.",
            created_at=NOW,
            updated_at=None,
        ),
        sent_at=None,
        sent_by=None,
    )
    summary = entry.summarize()
    assert summary.draft_id == UUID
    assert summary.subject == "Hello"
    assert summary.body_size == len("A draft body.")
    assert summary.created_at == NOW
    assert summary.updated_at is None


def test_swarm_summary_derives_num_agents() -> None:
    swarm = MAILSwarm(
        name="chorus",
        description="A test swarm.",
        keywords=["testing"],
        agents=["sage", "muse"],
        metadata={"k": "v"},
    )
    summary = swarm.summarize()
    assert summary.name == "chorus"
    assert summary.description == "A test swarm."
    assert summary.keywords == ["testing"]
    assert summary.num_agents == 2
