# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Row <-> MAIL Pydantic model conversion for the SQLite backend.

This module centralizes the *hybrid* invariant in one place: every entity row
carries a ``body`` JSON column equal to ``model.model_dump(mode="json")`` plus a
handful of typed columns used only for ``WHERE`` / ``ORDER BY``. Each table gets
a pair of helpers:

- ``<table>_to_columns(model)`` — the keyword arguments to construct (or update)
  a ``*Row``: the derived typed columns *and* ``body``. The typed columns are
  always computed from the model, never the other way around, so they can never
  drift from the body.
- ``<table>_from_row(row)`` — rehydrate the model. This reads **only**
  ``row.body`` via ``Model.model_validate(...)``; the typed columns are never
  consulted on read. That is what makes the schema tolerant of model evolution:
  adding a field to a MAIL model needs a schema change only if the new field
  must become queryable.

``mailbox_items`` and ``message_buffer`` carry no JSON body and have no MAIL
model — they are pure membership / ordering rows constructed directly by the
repositories, so they have no serializer here.

See ``src/mail/server/docs/reference/backends.md`` for the backend overview.
"""

from __future__ import annotations

from typing import Any

from mail_protocol.core.drafts import MAILDraftsEntry
from mail_protocol.core.inbox import MAILInboxEntrySummary
from mail_protocol.core.lists import MAILListInBackend
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.trash import MAILTrashEntry
from mail_protocol.core.user_agents import MAILUserAgentInBackend
from mail_protocol.core.webhooks import MAILWebhook

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

# --------------------------------------------------------------------------- #
# user_agents
# --------------------------------------------------------------------------- #


def user_agent_to_columns(model: MAILUserAgentInBackend) -> dict[str, Any]:
    ua = model.user_agent
    return {
        "address": model.get_address(),
        "ua_type": ua.ua_type,
        # ``swarm`` is meaningful only for agents; users/admins/daemons have none.
        "swarm": getattr(ua, "swarm", None),
        "host": ua.host,
        "hashed_password": model.hashed_password,
        "body": model.model_dump(mode="json"),
    }


def user_agent_from_row(row: UserAgentRow) -> MAILUserAgentInBackend:
    return MAILUserAgentInBackend.model_validate(row.body)


# --------------------------------------------------------------------------- #
# swarms
# --------------------------------------------------------------------------- #


def swarm_to_columns(model: MAILSwarm) -> dict[str, Any]:
    return {
        "name": model.name,
        "body": model.model_dump(mode="json"),
    }


def swarm_from_row(row: SwarmRow) -> MAILSwarm:
    return MAILSwarm.model_validate(row.body)


# --------------------------------------------------------------------------- #
# messages
# --------------------------------------------------------------------------- #


def message_to_columns(model: MAILMessage) -> dict[str, Any]:
    return {
        "message_id": model.message_id,
        "sender": model.sender,
        "subject": model.subject,
        "reply_to": model.reply_to,
        "sent_at": model.sent_at,
        "body": model.model_dump(mode="json"),
    }


def message_from_row(row: MessageRow) -> MAILMessage:
    return MAILMessage.model_validate(row.body)


# --------------------------------------------------------------------------- #
# inbox_entries (shared summary, keyed by message id)
# --------------------------------------------------------------------------- #


def inbox_entry_to_columns(model: MAILInboxEntrySummary) -> dict[str, Any]:
    return {
        "message_id": model.message_id,
        "sender": model.sender,
        "subject": model.subject,
        "body_size": model.body_size,
        "received_at": model.received_at,
        "delivered_by": model.delivered_by,
        "body": model.model_dump(mode="json"),
    }


def inbox_entry_from_row(row: InboxEntryRow) -> MAILInboxEntrySummary:
    return MAILInboxEntrySummary.model_validate(row.body)


# --------------------------------------------------------------------------- #
# outbox_entries (shared summary, keyed by message id)
# --------------------------------------------------------------------------- #


def outbox_entry_to_columns(model: MAILOutboxEntrySummary) -> dict[str, Any]:
    return {
        "message_id": model.message_id,
        "sent_at": model.sent_at,
        "delivered_at": model.delivered_at,
        "delivered_by": model.delivered_by,
        "body": model.model_dump(mode="json"),
    }


def outbox_entry_from_row(row: OutboxEntryRow) -> MAILOutboxEntrySummary:
    return MAILOutboxEntrySummary.model_validate(row.body)


# --------------------------------------------------------------------------- #
# draft_entries
# --------------------------------------------------------------------------- #


def draft_entry_to_columns(model: MAILDraftsEntry) -> dict[str, Any]:
    return {
        "draft_id": model.draft.draft_id,
        "created_at": model.draft.created_at,
        "updated_at": model.draft.updated_at,
        "body": model.model_dump(mode="json"),
    }


def draft_entry_from_row(row: DraftEntryRow) -> MAILDraftsEntry:
    return MAILDraftsEntry.model_validate(row.body)


# --------------------------------------------------------------------------- #
# trash_entries (shared, keyed by message id)
# --------------------------------------------------------------------------- #


def trash_entry_to_columns(model: MAILTrashEntry) -> dict[str, Any]:
    return {
        "message_id": model.message.message_id,
        "trashed_at": model.trashed_at,
        "body": model.model_dump(mode="json"),
    }


def trash_entry_from_row(row: TrashEntryRow) -> MAILTrashEntry:
    return MAILTrashEntry.model_validate(row.body)


# --------------------------------------------------------------------------- #
# webhooks (keyed by URL)
# --------------------------------------------------------------------------- #


def webhook_to_columns(model: MAILWebhook) -> dict[str, Any]:
    return {
        "url": model.url,
        "webhook_id": model.webhook_id,
        "body": model.model_dump(mode="json"),
    }


def webhook_from_row(row: WebhookRow) -> MAILWebhook:
    return MAILWebhook.model_validate(row.body)


# --------------------------------------------------------------------------- #
# lists (members live inside the body)
# --------------------------------------------------------------------------- #


def list_to_columns(model: MAILListInBackend) -> dict[str, Any]:
    return {
        "address": model.get_address(),
        "list_id": model.list_id,
        "swarm": model.swarm,
        "host": model.host,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
        "body": model.model_dump(mode="json"),
    }


def list_from_row(row: ListRow) -> MAILListInBackend:
    return MAILListInBackend.model_validate(row.body)
