# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Declarative SQLAlchemy schema for the MAIL SQLite backend.

Every entity row follows the *hybrid* convention: typed, indexed columns for
the handful of fields that the backend filters, sorts, or paginates on, plus a
``body`` JSON column holding the full MAIL Pydantic model
(``model.model_dump(mode="json")``). Reads always rehydrate the model from
``body`` via ``Model.model_validate(...)`` — the typed columns exist only for
``WHERE`` / ``ORDER BY``. Adding a field to a MAIL model therefore needs a
schema change only when that field must become queryable.

See ``src/mail/server/docs/reference/backends.md`` for the backend overview.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""

    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UserAgentRow(Base):
    """A MAIL user-agent (agent / user / admin / daemon)."""

    __tablename__ = "user_agents"

    # Full MAIL address: ``name@swarm@host`` for agents,
    # ``prefix:name@host`` for users / admins / daemons.
    address: Mapped[str] = mapped_column(String(512), primary_key=True)
    ua_type: Mapped[str] = mapped_column(String(16), index=True)
    # Swarm is only meaningful for agents; null for user / admin / daemon.
    swarm: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    host: Mapped[str] = mapped_column(String(255), index=True)
    hashed_password: Mapped[str] = mapped_column(Text)
    # Full ``MAILUserAgentInBackend``.
    body: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SwarmRow(Base):
    """A MAIL swarm exposed by this server."""

    __tablename__ = "swarms"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    # Full ``MAILSwarm``.
    body: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class MessageRow(Base):
    """The canonical store of every MAIL message known to this server."""

    __tablename__ = "messages"

    # Bare UUID, as stored on ``MAILMessage.message_id`` (no ``msg_`` prefix).
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sender: Mapped[str] = mapped_column(String(512), index=True)
    subject: Mapped[str] = mapped_column(Text)
    reply_to: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Full ``MAILMessage`` (recipients, tags, metadata, body text).
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class InboxEntryRow(Base):
    """
    A shared inbox-entry summary, keyed globally by message id.

    Mirrors the memory backend: when a message fans out to N recipients they
    share one entry row; the per-owner data is the *membership*
    (``mailbox_items``), not the entry.
    """

    __tablename__ = "inbox_entries"

    message_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        primary_key=True,
    )
    sender: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(Text)
    body_size: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    delivered_by: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Full ``MAILInboxEntrySummary``.
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class OutboxEntryRow(Base):
    """A shared outbox-entry summary, keyed globally by message id."""

    __tablename__ = "outbox_entries"

    message_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        primary_key=True,
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_by: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Full ``MAILOutboxEntrySummary``.
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class DraftEntryRow(Base):
    """A draft-box entry, keyed by draft id."""

    __tablename__ = "draft_entries"

    draft_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Full ``MAILDraftsEntry``.
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class TrashEntryRow(Base):
    """A shared trash-entry, keyed globally by message id."""

    __tablename__ = "trash_entries"

    message_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        primary_key=True,
    )
    trashed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Full ``MAILTrashEntry``.
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class MailboxItemRow(Base):
    """
    Unified per-owner box membership + ordering for all four boxes.

    One row links an owner's box to an entry. ``box`` discriminates between
    ``inbox`` / ``outbox`` / ``drafts`` / ``trash``; ``item_id`` is a message
    id (inbox / outbox / trash) or a draft id (drafts). The autoincrement
    ``id`` reproduces the insertion order that the memory backend got for free
    from Python lists, and serves as the stable tiebreaker when two entries
    share an ``entered_at``.
    """

    __tablename__ = "mailbox_items"
    __table_args__ = (
        UniqueConstraint(
            "owner_address",
            "box",
            "item_id",
            name="uq_mailbox_items_owner_box_item",
        ),
        Index("ix_mailbox_items_owner_box", "owner_address", "box"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_address: Mapped[str] = mapped_column(
        String(512),
        ForeignKey("user_agents.address", ondelete="CASCADE"),
        index=True,
    )
    box: Mapped[str] = mapped_column(String(8))
    item_id: Mapped[str] = mapped_column(String(64))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MessageBufferRow(Base):
    """The FIFO message delivery queue. Autoincrement ``id`` preserves order."""

    __tablename__ = "message_buffer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class WebhookRow(Base):
    """A server webhook, keyed by URL (matching the memory backend)."""

    __tablename__ = "webhooks"

    url: Mapped[str] = mapped_column(String(512), primary_key=True)
    webhook_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    # Full ``MAILWebhook`` (events, secret).
    body: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RefreshTokenRow(Base):
    """
    A stored refresh token, keyed by its hash.

    Unlike the entity rows, this table has **no** ``body`` JSON column: the
    ``RefreshTokenRecord`` model is tiny and every field is queried directly, so
    all columns are typed (mirroring ``mailbox_items`` / ``message_buffer``).
    ``owner_address`` cascades on user-agent deletion, so removing a principal
    drops their refresh tokens for free.
    """

    __tablename__ = "refresh_tokens"

    # sha256 hex of the plaintext token.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_address: Mapped[str] = mapped_column(
        String(512),
        ForeignKey("user_agents.address", ondelete="CASCADE"),
        index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked: Mapped[bool] = mapped_column(default=False)
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ListRow(Base):
    """A MAIL list. Members live inside ``body``, mirroring the memory backend."""

    __tablename__ = "lists"

    # ``list:<name>@<swarm>@<host>``.
    address: Mapped[str] = mapped_column(String(512), primary_key=True)
    list_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    swarm: Mapped[str] = mapped_column(String(128), index=True)
    host: Mapped[str] = mapped_column(String(255))
    # Full ``MAILListInBackend`` (members, policy, owner).
    body: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
