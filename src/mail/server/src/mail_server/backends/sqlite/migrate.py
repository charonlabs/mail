# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
One-time import of a filesystem (memory-backend) deployment into SQLite.

The memory backend persists its state as a directory tree under
``~/.mail-swarms/deployments/<deployment>/``. This module reads that tree with
the memory backend's own loaders (so the on-disk format can never drift) and
writes every collection into the SQLite store in a single transaction.

The per-owner box ordering that the memory backend kept implicitly (Python list
order) is reconstructed by inserting ``mailbox_items`` membership rows in list
order, each stamped with the box-arrival timestamp drawn from its entry
(``received_at`` / ``sent_at`` / ``draft.created_at`` / ``trashed_at``), so the
autoincrement ``id`` tiebreaker reproduces the original order.

The import refuses to run against a non-empty database, so it can't clobber an
existing SQLite deployment. See ``src/mail/server/docs/reference/backends.md``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import mail_server.backends.memory.fs as memory_fs
from mail_server.backends.sqlite.database import Database
from mail_server.backends.sqlite.init import default_sqlite_path
from mail_server.backends.sqlite.repositories import (
    BOX_DRAFTS,
    BOX_INBOX,
    BOX_OUTBOX,
    BOX_TRASH,
    MailStore,
)
from mail_server.backends.sqlite.schema import (
    ListRow,
    MessageRow,
    SwarmRow,
    UserAgentRow,
    WebhookRow,
)

logger = logging.getLogger(__name__)


def _memory_deployment_dir(deployment: str) -> Path:
    return Path.home().joinpath(".mail-swarms", "deployments", deployment)


async def _is_empty(session: AsyncSession) -> bool:
    """True if no top-level collection has any rows yet."""

    for row_cls in (UserAgentRow, SwarmRow, MessageRow, WebhookRow, ListRow):
        count = await session.scalar(select(func.count()).select_from(row_cls))
        if count:
            return False
    return True


async def import_memory_deployment(
    deployment: str = "default",
    source_dir: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, int]:
    """
    Import a filesystem deployment into a fresh SQLite database.

    ``source_dir`` defaults to ``~/.mail-swarms/deployments/<deployment>`` (the
    memory backend's tree); ``db_path`` defaults to ``<that dir>/mail.db``.
    Returns per-collection row counts. Raises if the source is missing or the
    target database already holds data.
    """

    source_dir = source_dir or _memory_deployment_dir(deployment)
    if not source_dir.is_dir():
        raise FileNotFoundError(
            f"no filesystem deployment to import at {source_dir}"
        )
    db_path = db_path or default_sqlite_path(deployment)

    # Load every collection via the memory backend's loaders by pointing them at
    # the source tree (mirrors how the test harness redirects persistence).
    previous_path = memory_fs.DEPLOYMENT_PATH
    memory_fs.DEPLOYMENT_PATH = source_dir
    try:
        user_agents = await memory_fs.load_user_agents()
        swarms = await memory_fs.load_swarms()
        messages = await memory_fs.load_messages()
        inbox_entries = await memory_fs.load_inbox_entries()
        inboxes = await memory_fs.load_inboxes()
        outbox_entries = await memory_fs.load_outbox_entries()
        outboxes = await memory_fs.load_outboxes()
        draft_entries = await memory_fs.load_draft_entries()
        drafts = await memory_fs.load_drafts()
        trash_entries = await memory_fs.load_trash_entries()
        trashes = await memory_fs.load_trashes()
        message_buffer = await memory_fs.load_message_buffer()
        webhooks = await memory_fs.load_webhooks()
        lists = await memory_fs.load_lists()
    finally:
        memory_fs.DEPLOYMENT_PATH = previous_path

    db = Database(f"sqlite:///{db_path}")
    await db.create_schema()
    try:
        async with db.session() as session:
            if not await _is_empty(session):
                raise ValueError(
                    f"target sqlite database {db_path} is not empty; "
                    "refusing to import"
                )
            store = MailStore(session)

            for ua_in_be in user_agents.values():
                await store.user_agents.add(ua_in_be)
            for swarm in swarms.values():
                await store.swarms.add(swarm)

            # Canonical messages first (box entries FK onto them). Track which
            # ids exist so we never insert an entry whose message is absent.
            present: set[str] = set()
            for message in messages.values():
                await store.messages.add(message)
                present.add(message.message_id)

            for entry in inbox_entries.values():
                if entry.message_id in present:
                    await store.boxes.upsert_inbox_entry(entry)
            for entry in outbox_entries.values():
                if entry.message_id in present:
                    await store.boxes.upsert_outbox_entry(entry)
            for trash_entry in trash_entries.values():
                # Trash entries carry the full message; restore it if the
                # canonical row was already gone.
                if trash_entry.message.message_id not in present:
                    await store.messages.add(trash_entry.message)
                    present.add(trash_entry.message.message_id)
                await store.boxes.upsert_trash_entry(trash_entry)
            for draft_entry in draft_entries.values():
                await store.boxes.upsert_draft_entry(draft_entry)

            await _import_membership(
                store, BOX_INBOX, inboxes, inbox_entries, lambda e: e.received_at
            )
            await _import_membership(
                store, BOX_OUTBOX, outboxes, outbox_entries, lambda e: e.sent_at
            )
            await _import_membership(
                store,
                BOX_DRAFTS,
                drafts,
                draft_entries,
                lambda e: e.draft.created_at,
            )
            await _import_membership(
                store, BOX_TRASH, trashes, trash_entries, lambda e: e.trashed_at
            )

            for message_id in message_buffer:
                await store.buffer.enqueue(message_id)
            for webhook in webhooks.values():
                await store.webhooks.add(webhook)
            for mail_list in lists.values():
                await store.lists.add(mail_list)
    finally:
        await db.dispose()

    counts = {
        "user_agents": len(user_agents),
        "swarms": len(swarms),
        "messages": len(messages),
        "inbox_entries": len(inbox_entries),
        "outbox_entries": len(outbox_entries),
        "draft_entries": len(draft_entries),
        "trash_entries": len(trash_entries),
        "webhooks": len(webhooks),
        "lists": len(lists),
        "buffered": len(message_buffer),
    }
    logger.info("imported filesystem deployment %s into %s: %s", deployment, db_path, counts)
    return counts


async def _import_membership(
    store: MailStore,
    box: str,
    boxes: dict[str, list[str]],
    entries: dict[str, Any],
    entered_at_of: Callable[[Any], datetime],
) -> None:
    """
    Recreate ``mailbox_items`` rows for one box from its per-owner id lists.

    Insertion follows list order, so the autoincrement ``id`` reproduces the
    memory backend's insertion-order tiebreaker. The arrival timestamp is read
    from each item's entry via ``entered_at_of``; items missing an entry (or
    already present) are skipped.
    """

    for owner, item_ids in boxes.items():
        for item_id in item_ids:
            entry = entries.get(item_id)
            if entry is None:
                logger.warning(
                    "skipping %s membership for %s: no entry for item %s",
                    box,
                    owner,
                    item_id,
                )
                continue
            if await store.boxes.is_member(owner, box, item_id):
                continue
            await store.boxes.add_membership(
                owner, box, item_id, entered_at_of(entry)
            )
