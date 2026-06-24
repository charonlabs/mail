# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Database-level guarantees for the sqlite backend: the connection pragmas, the
all-or-nothing transaction boundary around a multi-write operation, and that
concurrent writers don't trip ``database is locked`` (WAL + busy_timeout).
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
)
from mail_protocol.network.requests import (
    AdminUserPostRequest,
    BoxFilterParams,
    DraftPostRequest,
    DraftSendPostRequest,
)
from mail_server.backends.sqlite.api import SQLiteBackend
from mail_server.backends.sqlite.database import Database
from mail_server.backends.sqlite.repositories import (
    MailStore,
    MessageBufferRepository,
)
from sqlalchemy import text

ADMIN = MAILAdmin(ua_type="admin", admin_id="ryan", host="localhost")
ALICE = MAILUserAgent(
    user_agent=MAILUser(ua_type="user", user_id="alice", host="localhost")
)


@pytest.fixture
async def backend(tmp_path: Path) -> AsyncIterator[SQLiteBackend]:
    be = SQLiteBackend(f"sqlite:///{tmp_path / 'mail.db'}")
    await be.on_server_startup(host="localhost")
    await be.admin_post_user(
        ADMIN, AdminUserPostRequest(user_id="alice", user_password="pw")
    )
    yield be
    await be.on_server_shutdown()


async def test_connection_pragmas_applied(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'mail.db'}")
    await db.create_schema()
    try:
        async with db.session() as session:
            journal_mode = (await session.execute(text("PRAGMA journal_mode"))).scalar()
            foreign_keys = (await session.execute(text("PRAGMA foreign_keys"))).scalar()
            busy_timeout = (await session.execute(text("PRAGMA busy_timeout"))).scalar()
    finally:
        await db.dispose()

    assert journal_mode == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 5000


async def test_send_draft_rolls_back_on_failure(
    backend: SQLiteBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure on the final write of ``send_draft`` leaves no partial rows."""

    entry = await backend.post_draft(
        ALICE, DraftPostRequest(subject="Tx", body="atomic")
    )
    draft_id = entry.draft.draft_id

    async def _boom(self: MessageBufferRepository, message_id: str) -> None:
        raise RuntimeError("buffer write failed")

    # Fail on the last step (buffer enqueue), after message/outbox/membership.
    monkeypatch.setattr(MessageBufferRepository, "enqueue", _boom)

    with pytest.raises(RuntimeError, match="buffer write failed"):
        await backend.send_draft(
            ALICE, draft_id, DraftSendPostRequest(recipients=["user:alice@localhost"])
        )

    # Nothing from the aborted send survived: no outbox entry, empty buffer.
    _, outbox_total = await backend.get_outbox(ALICE, BoxFilterParams())
    assert outbox_total == 0
    async with backend._db.session() as session:
        assert await MailStore(session).buffer.list_ids() == []
    # ...and the draft is untouched, so the send can be retried.
    assert (await backend.get_draft(ALICE, draft_id)).draft.draft_id == draft_id


async def test_concurrent_sends_do_not_lock(backend: SQLiteBackend) -> None:
    """WAL + busy_timeout: concurrent committed sends don't raise locked."""

    drafts = [
        await backend.post_draft(
            ALICE, DraftPostRequest(subject=f"D{i}", body="body")
        )
        for i in range(8)
    ]

    messages = await asyncio.gather(
        *(
            backend.send_draft(
                ALICE,
                entry.draft.draft_id,
                DraftSendPostRequest(recipients=["user:alice@localhost"]),
            )
            for entry in drafts
        )
    )

    # Every send committed a distinct message into the delivery buffer.
    assert len({m.message_id for m in messages}) == 8
    daemon = MAILDaemon(ua_type="daemon", worker_name="dummy", host="localhost")
    buffered = await backend.daemon_clear_message_buffer(daemon)
    assert sorted(buffered) == sorted(m.message_id for m in messages)
