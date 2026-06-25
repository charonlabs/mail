# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Session-scoped repositories for the MAIL SQLite backend.

Mirrors the chorus repository pattern: a top-level ``MailStore(session)`` frozen
dataclass exposes sub-repositories as properties, each a frozen dataclass
wrapping the *same* ``AsyncSession``. Repositories own **SQL only** —
``select`` / ``insert`` / ``update`` / ``delete``, pagination, and ordering —
and return MAIL Pydantic models (via ``serializers``), never ORM rows. They call
``session.flush()`` (never ``commit()``); the ``Database.session()`` context
manager owns the transaction boundary, so several repository calls compose into
one atomic operation.

``MailboxRepository`` is the workhorse: it unifies the four boxes (inbox,
outbox, drafts, trash) over the shared ``mailbox_items`` membership table plus
the per-box entry tables, pushing sorting/pagination into ``ORDER BY ... LIMIT
/ OFFSET`` instead of loading whole boxes into Python.

See ``src/mail/server/docs/reference/backends.md`` for the backend overview.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mail_protocol.core.drafts import MAILDraftsEntry, MAILDraftsEntrySummary
from mail_protocol.core.inbox import MAILInboxEntrySummary
from mail_protocol.core.lists import MAILListInBackend
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.trash import MAILTrashEntry, MAILTrashEntrySummary
from mail_protocol.core.user_agents import MAILUserAgentInBackend
from mail_protocol.core.webhooks import MAILWebhook
from mail_protocol.network.requests import BoxFilterParams
from sqlalchemy import asc, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mail_server.backends.sqlite import serializers as ser
from mail_server.backends.sqlite.schema import (
    DraftEntryRow,
    InboxEntryRow,
    ListRow,
    MailboxItemRow,
    MessageBufferRow,
    MessageRow,
    OutboxEntryRow,
    SwarmRow,
    TrashEntryRow,
    UserAgentRow,
    WebhookRow,
)

# Box discriminators stored in ``mailbox_items.box``.
BOX_INBOX = "inbox"
BOX_OUTBOX = "outbox"
BOX_DRAFTS = "drafts"
BOX_TRASH = "trash"


@dataclass(frozen=True)
class MailStore:
    """Root handle wrapping a single session; hands out sub-repositories."""

    session: AsyncSession

    @property
    def user_agents(self) -> UserAgentRepository:
        return UserAgentRepository(self.session)

    @property
    def swarms(self) -> SwarmRepository:
        return SwarmRepository(self.session)

    @property
    def messages(self) -> MessageRepository:
        return MessageRepository(self.session)

    @property
    def boxes(self) -> MailboxRepository:
        return MailboxRepository(self.session)

    @property
    def buffer(self) -> MessageBufferRepository:
        return MessageBufferRepository(self.session)

    @property
    def webhooks(self) -> WebhookRepository:
        return WebhookRepository(self.session)

    @property
    def lists(self) -> ListRepository:
        return ListRepository(self.session)


# --------------------------------------------------------------------------- #
# user_agents
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class UserAgentRepository:
    session: AsyncSession

    async def get(self, address: str) -> MAILUserAgentInBackend | None:
        row = await self.session.get(UserAgentRow, address)
        if row is None:
            return None
        return ser.user_agent_from_row(row)

    async def exists(self, address: str) -> bool:
        result = await self.session.scalar(
            select(UserAgentRow.address).where(UserAgentRow.address == address)
        )
        return result is not None

    async def list_by_type(self, ua_type: str) -> list[MAILUserAgentInBackend]:
        rows = await self.session.scalars(
            select(UserAgentRow)
            .where(UserAgentRow.ua_type == ua_type)
            .order_by(UserAgentRow.created_at, UserAgentRow.address)
        )
        return [ser.user_agent_from_row(row) for row in rows]

    async def add(self, model: MAILUserAgentInBackend) -> MAILUserAgentInBackend:
        self.session.add(UserAgentRow(**ser.user_agent_to_columns(model)))
        await self.session.flush()
        return model

    async def delete(self, address: str) -> MAILUserAgentInBackend | None:
        row = await self.session.get(UserAgentRow, address)
        if row is None:
            return None
        model = ser.user_agent_from_row(row)
        await self.session.delete(row)
        await self.session.flush()
        return model

    async def set_password(
        self, address: str, hashed_password: str
    ) -> MAILUserAgentInBackend | None:
        """Rewrite the password hash in both the typed column and the body."""

        row = await self.session.get(UserAgentRow, address)
        if row is None:
            return None
        model = ser.user_agent_from_row(row)
        model.hashed_password = hashed_password
        cols = ser.user_agent_to_columns(model)
        row.hashed_password = cols["hashed_password"]
        row.body = cols["body"]
        await self.session.flush()
        return model


# --------------------------------------------------------------------------- #
# swarms
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SwarmRepository:
    session: AsyncSession

    async def list_all(self) -> list[MAILSwarm]:
        rows = await self.session.scalars(
            select(SwarmRow).order_by(SwarmRow.created_at, SwarmRow.name)
        )
        return [ser.swarm_from_row(row) for row in rows]

    async def get(self, name: str) -> MAILSwarm | None:
        row = await self.session.get(SwarmRow, name)
        if row is None:
            return None
        return ser.swarm_from_row(row)

    async def add(self, model: MAILSwarm) -> MAILSwarm:
        self.session.add(SwarmRow(**ser.swarm_to_columns(model)))
        await self.session.flush()
        return model

    async def delete(self, name: str) -> MAILSwarm | None:
        row = await self.session.get(SwarmRow, name)
        if row is None:
            return None
        model = ser.swarm_from_row(row)
        await self.session.delete(row)
        await self.session.flush()
        return model


# --------------------------------------------------------------------------- #
# messages (canonical store)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MessageRepository:
    session: AsyncSession

    async def get(self, message_id: str) -> MAILMessage | None:
        row = await self.session.get(MessageRow, message_id)
        if row is None:
            return None
        return ser.message_from_row(row)

    async def add(self, model: MAILMessage) -> MAILMessage:
        self.session.add(MessageRow(**ser.message_to_columns(model)))
        await self.session.flush()
        return model

    async def delete(self, message_id: str) -> bool:
        row = await self.session.get(MessageRow, message_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True


# --------------------------------------------------------------------------- #
# boxes — mailbox_items membership + the four entry tables
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MailboxRepository:
    session: AsyncSession

    #
    # Membership (mailbox_items)
    #
    async def is_member(self, owner: str, box: str, item_id: str) -> bool:
        result = await self.session.scalar(
            select(MailboxItemRow.id).where(
                MailboxItemRow.owner_address == owner,
                MailboxItemRow.box == box,
                MailboxItemRow.item_id == item_id,
            )
        )
        return result is not None

    async def add_membership(
        self, owner: str, box: str, item_id: str, entered_at: datetime
    ) -> None:
        self.session.add(
            MailboxItemRow(
                owner_address=owner,
                box=box,
                item_id=item_id,
                entered_at=entered_at,
            )
        )
        await self.session.flush()

    async def remove_membership(self, owner: str, box: str, item_id: str) -> bool:
        """Delete one membership row; return whether it existed."""

        if not await self.is_member(owner, box, item_id):
            return False
        await self.session.execute(
            delete(MailboxItemRow).where(
                MailboxItemRow.owner_address == owner,
                MailboxItemRow.box == box,
                MailboxItemRow.item_id == item_id,
            )
        )
        await self.session.flush()
        return True

    async def list_item_ids(self, owner: str, box: str) -> list[str]:
        """Item ids in a box, in insertion order (used by ``clear_trash``)."""

        rows = await self.session.scalars(
            select(MailboxItemRow.item_id)
            .where(
                MailboxItemRow.owner_address == owner,
                MailboxItemRow.box == box,
            )
            .order_by(asc(MailboxItemRow.id))
        )
        return list(rows)

    async def count_item_members(self, box: str, item_id: str) -> int:
        """How many owners still reference ``item_id`` in ``box`` (orphan check)."""

        result = await self.session.scalar(
            select(func.count())
            .select_from(MailboxItemRow)
            .where(MailboxItemRow.box == box, MailboxItemRow.item_id == item_id)
        )
        return result or 0

    async def _count(self, owner: str, box: str) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(MailboxItemRow)
            .where(
                MailboxItemRow.owner_address == owner,
                MailboxItemRow.box == box,
            )
        )
        return result or 0

    #
    # Paginated reads
    #
    async def _page(
        self,
        *,
        owner: str,
        box: str,
        entry_cls: Any,
        entry_pk: Any,
        filters: BoxFilterParams,
        allow_message_sort: bool,
    ) -> tuple[list[Any], int]:
        """
        Return one ordered, sliced page of entry rows + the full box count.

        ``entered_at`` sorts by ``mailbox_items.entered_at`` (the box-arrival
        time); ``sent_at`` joins ``messages`` and sorts by the original send
        time — only valid for boxes whose items are real messages
        (``allow_message_sort``). ``mailbox_items.id`` is the always-ascending
        tiebreaker, reproducing the memory backend's stable insertion order.
        """

        total = await self._count(owner, box)
        if total == 0:
            return [], total

        stmt = (
            select(entry_cls)
            .join(MailboxItemRow, MailboxItemRow.item_id == entry_pk)
            .where(
                MailboxItemRow.owner_address == owner,
                MailboxItemRow.box == box,
            )
        )

        if allow_message_sort and filters.sort_by == "sent_at":
            stmt = stmt.join(
                MessageRow, MessageRow.message_id == MailboxItemRow.item_id
            )
            sort_col: Any = MessageRow.sent_at
        else:
            sort_col = MailboxItemRow.entered_at

        sort_col = sort_col.desc() if filters.order == "desc" else sort_col.asc()
        stmt = (
            stmt.order_by(sort_col, asc(MailboxItemRow.id))
            .limit(filters.limit)
            .offset(filters.offset)
        )

        rows = list(await self.session.scalars(stmt))
        return rows, total

    async def list_inbox(
        self, owner: str, filters: BoxFilterParams
    ) -> tuple[list[MAILInboxEntrySummary], int]:
        rows, total = await self._page(
            owner=owner,
            box=BOX_INBOX,
            entry_cls=InboxEntryRow,
            entry_pk=InboxEntryRow.message_id,
            filters=filters,
            allow_message_sort=True,
        )
        return [ser.inbox_entry_from_row(row) for row in rows], total

    async def list_outbox(
        self, owner: str, filters: BoxFilterParams
    ) -> tuple[list[MAILOutboxEntrySummary], int]:
        rows, total = await self._page(
            owner=owner,
            box=BOX_OUTBOX,
            entry_cls=OutboxEntryRow,
            entry_pk=OutboxEntryRow.message_id,
            filters=filters,
            allow_message_sort=True,
        )
        return [ser.outbox_entry_from_row(row) for row in rows], total

    async def list_drafts(
        self, owner: str, filters: BoxFilterParams
    ) -> tuple[list[MAILDraftsEntrySummary], int]:
        # Drafts have no send time; ``sort_by=sent_at`` is rejected at the
        # router, so only ``entered_at`` (== created_at) ordering reaches here.
        rows, total = await self._page(
            owner=owner,
            box=BOX_DRAFTS,
            entry_cls=DraftEntryRow,
            entry_pk=DraftEntryRow.draft_id,
            filters=filters,
            allow_message_sort=False,
        )
        return [ser.draft_entry_from_row(row).summarize() for row in rows], total

    async def list_trash(
        self, owner: str, filters: BoxFilterParams
    ) -> tuple[list[MAILTrashEntrySummary], int]:
        rows, total = await self._page(
            owner=owner,
            box=BOX_TRASH,
            entry_cls=TrashEntryRow,
            entry_pk=TrashEntryRow.message_id,
            filters=filters,
            allow_message_sort=True,
        )
        return [ser.trash_entry_from_row(row).summarize() for row in rows], total

    #
    # inbox_entries (shared, keyed by message id)
    #
    async def get_inbox_entry(self, message_id: str) -> MAILInboxEntrySummary | None:
        row = await self.session.get(InboxEntryRow, message_id)
        if row is None:
            return None
        return ser.inbox_entry_from_row(row)

    async def upsert_inbox_entry(self, summary: MAILInboxEntrySummary) -> None:
        cols = ser.inbox_entry_to_columns(summary)
        row = await self.session.get(InboxEntryRow, summary.message_id)
        if row is None:
            self.session.add(InboxEntryRow(**cols))
        else:
            for key, value in cols.items():
                setattr(row, key, value)
        await self.session.flush()

    async def delete_inbox_entry(self, message_id: str) -> None:
        row = await self.session.get(InboxEntryRow, message_id)
        if row is not None:
            await self.session.delete(row)
            await self.session.flush()

    #
    # outbox_entries (shared, keyed by message id)
    #
    async def get_outbox_entry(self, message_id: str) -> MAILOutboxEntrySummary | None:
        row = await self.session.get(OutboxEntryRow, message_id)
        if row is None:
            return None
        return ser.outbox_entry_from_row(row)

    async def upsert_outbox_entry(self, summary: MAILOutboxEntrySummary) -> None:
        cols = ser.outbox_entry_to_columns(summary)
        row = await self.session.get(OutboxEntryRow, summary.message_id)
        if row is None:
            self.session.add(OutboxEntryRow(**cols))
        else:
            for key, value in cols.items():
                setattr(row, key, value)
        await self.session.flush()

    #
    # draft_entries (keyed by draft id)
    #
    async def get_draft_entry(self, draft_id: str) -> MAILDraftsEntry | None:
        row = await self.session.get(DraftEntryRow, draft_id)
        if row is None:
            return None
        return ser.draft_entry_from_row(row)

    async def upsert_draft_entry(self, entry: MAILDraftsEntry) -> None:
        cols = ser.draft_entry_to_columns(entry)
        row = await self.session.get(DraftEntryRow, entry.draft.draft_id)
        if row is None:
            self.session.add(DraftEntryRow(**cols))
        else:
            for key, value in cols.items():
                setattr(row, key, value)
        await self.session.flush()

    async def delete_draft_entry(self, draft_id: str) -> None:
        row = await self.session.get(DraftEntryRow, draft_id)
        if row is not None:
            await self.session.delete(row)
            await self.session.flush()

    #
    # trash_entries (shared, keyed by message id)
    #
    async def get_trash_entry(self, message_id: str) -> MAILTrashEntry | None:
        row = await self.session.get(TrashEntryRow, message_id)
        if row is None:
            return None
        return ser.trash_entry_from_row(row)

    async def upsert_trash_entry(self, entry: MAILTrashEntry) -> None:
        cols = ser.trash_entry_to_columns(entry)
        row = await self.session.get(TrashEntryRow, entry.message.message_id)
        if row is None:
            self.session.add(TrashEntryRow(**cols))
        else:
            for key, value in cols.items():
                setattr(row, key, value)
        await self.session.flush()

    async def delete_trash_entry(self, message_id: str) -> None:
        row = await self.session.get(TrashEntryRow, message_id)
        if row is not None:
            await self.session.delete(row)
            await self.session.flush()


# --------------------------------------------------------------------------- #
# message_buffer (FIFO delivery queue)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MessageBufferRepository:
    session: AsyncSession

    async def enqueue(self, message_id: str) -> None:
        self.session.add(MessageBufferRow(message_id=message_id))
        await self.session.flush()

    async def list_ids(self) -> list[str]:
        rows = await self.session.scalars(
            select(MessageBufferRow.message_id).order_by(asc(MessageBufferRow.id))
        )
        return list(rows)

    async def drain(self) -> list[str]:
        """Return every buffered id in FIFO order and clear the buffer atomically."""

        ids = await self.list_ids()
        if ids:
            await self.session.execute(delete(MessageBufferRow))
            await self.session.flush()
        return ids


# --------------------------------------------------------------------------- #
# webhooks (keyed by URL)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WebhookRepository:
    session: AsyncSession

    async def list_all(self) -> list[MAILWebhook]:
        rows = await self.session.scalars(
            select(WebhookRow).order_by(WebhookRow.created_at, WebhookRow.url)
        )
        return [ser.webhook_from_row(row) for row in rows]

    async def get_by_url(self, url: str) -> MAILWebhook | None:
        row = await self.session.get(WebhookRow, url)
        if row is None:
            return None
        return ser.webhook_from_row(row)

    async def get_by_id(self, webhook_id: str) -> MAILWebhook | None:
        row = await self.session.scalar(
            select(WebhookRow).where(WebhookRow.webhook_id == webhook_id)
        )
        if row is None:
            return None
        return ser.webhook_from_row(row)

    async def add(self, model: MAILWebhook) -> MAILWebhook:
        self.session.add(WebhookRow(**ser.webhook_to_columns(model)))
        await self.session.flush()
        return model

    async def delete_by_url(self, url: str) -> MAILWebhook | None:
        row = await self.session.get(WebhookRow, url)
        if row is None:
            return None
        model = ser.webhook_from_row(row)
        await self.session.delete(row)
        await self.session.flush()
        return model


# --------------------------------------------------------------------------- #
# lists (members live inside the body)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ListRepository:
    session: AsyncSession

    async def list_all(self) -> list[MAILListInBackend]:
        rows = await self.session.scalars(
            select(ListRow).order_by(ListRow.created_at, ListRow.address)
        )
        return [ser.list_from_row(row) for row in rows]

    async def get_by_address(self, address: str) -> MAILListInBackend | None:
        row = await self.session.get(ListRow, address)
        if row is None:
            return None
        return ser.list_from_row(row)

    async def add(self, model: MAILListInBackend) -> MAILListInBackend:
        self.session.add(ListRow(**ser.list_to_columns(model)))
        await self.session.flush()
        return model

    async def update(self, model: MAILListInBackend) -> MAILListInBackend:
        """Persist a mutated list (member edits, policy patch) by address."""

        cols = ser.list_to_columns(model)
        row = await self.session.get(ListRow, model.get_address())
        if row is None:
            self.session.add(ListRow(**cols))
        else:
            for key, value in cols.items():
                setattr(row, key, value)
        await self.session.flush()
        return model

    async def delete(self, address: str) -> MAILListInBackend | None:
        row = await self.session.get(ListRow, address)
        if row is None:
            return None
        model = ser.list_from_row(row)
        await self.session.delete(row)
        await self.session.flush()
        return model
