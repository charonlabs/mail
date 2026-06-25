# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Repository-layer tests for the SQLite backend, run against a real temp-file
database so foreign keys, datetime columns, and ordering behave as in prod.

The bulk pins ``MailboxRepository`` pagination: ``entered_at`` vs ``sent_at``
ordering, ``asc`` / ``desc``, ``limit`` / ``offset``, ``total`` correctness, and
the always-ascending ``id`` tiebreaker that reproduces the memory backend's
stable insertion order. The rest cover CRUD round-trips and the FIFO buffer.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mail_protocol.core.drafts import MAILDraft, MAILDraftsEntry
from mail_protocol.core.inbox import MAILInboxEntrySummary
from mail_protocol.core.lists import MAILList, MAILListInBackend
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.trash import MAILTrashEntry
from mail_protocol.core.user_agents import MAILAgent, MAILUserAgentInBackend
from mail_protocol.core.webhooks import MAILWebhook
from mail_protocol.network.requests import BoxFilterParams
from mail_server.backends.sqlite.database import Database
from mail_server.backends.sqlite.repositories import (
    BOX_INBOX,
    BOX_TRASH,
    MailStore,
)

OWNER = "sage@chorus@localhost"
SENDER = "user:alice@localhost"
DAEMON = "daemon:dummy@localhost"

T1 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
T2 = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
T3 = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(f"sqlite:///{tmp_path / 'mail.db'}")
    await database.create_schema()
    yield database
    await database.dispose()


def _uuid() -> str:
    return str(uuid.uuid4())


def _agent(owner: str = OWNER) -> MAILUserAgentInBackend:
    name, swarm, host = owner.split("@")
    return MAILUserAgentInBackend(
        user_agent=MAILAgent(ua_type="agent", name=name, swarm=swarm, host=host),
        hashed_password="hash",
    )


def _message(message_id: str, sent_at: datetime) -> MAILMessage:
    return MAILMessage(
        mail_version="2.0",
        message_id=message_id,
        sender=SENDER,
        recipients=[OWNER],
        subject="subject",
        body="body",
        tags=[],
        sent_at=sent_at,
        metadata={},
    )


async def _seed_inbox(
    store: MailStore, *, sent_at: datetime, entered_at: datetime
) -> str:
    """Create message + shared inbox entry + membership for OWNER; return id."""

    message_id = _uuid()
    await store.messages.add(_message(message_id, sent_at))
    await store.boxes.upsert_inbox_entry(
        MAILInboxEntrySummary(
            message_id=message_id,
            sender=SENDER,
            subject="subject",
            body_size=4,
            received_at=entered_at,
            delivered_by=DAEMON,
        )
    )
    await store.boxes.add_membership(OWNER, BOX_INBOX, message_id, entered_at)
    return message_id


# --------------------------------------------------------------------------- #
# MailboxRepository pagination / ordering
# --------------------------------------------------------------------------- #


async def test_inbox_default_orders_entered_at_desc(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        await store.user_agents.add(_agent())
        first = await _seed_inbox(store, sent_at=T1, entered_at=T1)
        second = await _seed_inbox(store, sent_at=T2, entered_at=T2)
        third = await _seed_inbox(store, sent_at=T3, entered_at=T3)

        page, total = await store.boxes.list_inbox(OWNER, BoxFilterParams())

        assert total == 3
        assert [e.message_id for e in page] == [third, second, first]


async def test_inbox_entered_at_asc(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        await store.user_agents.add(_agent())
        first = await _seed_inbox(store, sent_at=T1, entered_at=T1)
        second = await _seed_inbox(store, sent_at=T2, entered_at=T2)

        page, _ = await store.boxes.list_inbox(
            OWNER, BoxFilterParams(order="asc")
        )

        assert [e.message_id for e in page] == [first, second]


async def test_inbox_sort_by_sent_at_differs_from_entered_at(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        await store.user_agents.add(_agent())
        # Arrival order is the inverse of send order.
        late_arrival_old_send = await _seed_inbox(store, sent_at=T1, entered_at=T3)
        early_arrival_new_send = await _seed_inbox(store, sent_at=T3, entered_at=T1)

        by_entered, _ = await store.boxes.list_inbox(OWNER, BoxFilterParams())
        by_sent, _ = await store.boxes.list_inbox(
            OWNER, BoxFilterParams(sort_by="sent_at")
        )

        # entered_at desc -> the late arrival is first.
        assert [e.message_id for e in by_entered] == [
            late_arrival_old_send,
            early_arrival_new_send,
        ]
        # sent_at desc -> the newer send is first, flipping the order.
        assert [e.message_id for e in by_sent] == [
            early_arrival_new_send,
            late_arrival_old_send,
        ]


async def test_inbox_limit_offset_and_total(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        await store.user_agents.add(_agent())
        ids = [
            await _seed_inbox(store, sent_at=t, entered_at=t)
            for t in (T1, T2, T3)
        ]

        page, total = await store.boxes.list_inbox(
            OWNER, BoxFilterParams(limit=1, offset=1, order="asc")
        )

        assert total == 3  # count is the whole box, not the page
        assert [e.message_id for e in page] == [ids[1]]


async def test_inbox_tiebreak_is_insertion_order(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        await store.user_agents.add(_agent())
        # Identical entered_at; desc must still fall back to ascending id
        # (insertion order), matching the memory backend's stable sort.
        first = await _seed_inbox(store, sent_at=T1, entered_at=T1)
        second = await _seed_inbox(store, sent_at=T1, entered_at=T1)

        page, _ = await store.boxes.list_inbox(OWNER, BoxFilterParams())

        assert [e.message_id for e in page] == [first, second]


async def test_empty_box_returns_empty_page(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        await store.user_agents.add(_agent())

        page, total = await store.boxes.list_inbox(OWNER, BoxFilterParams())

        assert page == []
        assert total == 0


# --------------------------------------------------------------------------- #
# Membership / orphan accounting
# --------------------------------------------------------------------------- #


async def test_membership_add_remove_and_orphan_count(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        await store.user_agents.add(_agent())
        other = "echo@chorus@localhost"
        await store.user_agents.add(_agent(other))

        message_id = await _seed_inbox(store, sent_at=T1, entered_at=T1)
        # Fan the same shared entry out to a second owner.
        await store.boxes.add_membership(other, BOX_INBOX, message_id, T1)

        assert await store.boxes.count_item_members(BOX_INBOX, message_id) == 2
        assert await store.boxes.is_member(OWNER, BOX_INBOX, message_id)

        assert await store.boxes.remove_membership(OWNER, BOX_INBOX, message_id)
        assert not await store.boxes.is_member(OWNER, BOX_INBOX, message_id)
        assert await store.boxes.count_item_members(BOX_INBOX, message_id) == 1
        # Removing a non-member is a no-op returning False.
        assert not await store.boxes.remove_membership(OWNER, BOX_INBOX, message_id)


# --------------------------------------------------------------------------- #
# CRUD round-trips through real SQLite
# --------------------------------------------------------------------------- #


async def test_user_agent_crud(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        agent = _agent()
        await store.user_agents.add(agent)

        assert await store.user_agents.exists(OWNER)
        assert await store.user_agents.get(OWNER) == agent
        assert await store.user_agents.list_by_type("agent") == [agent]

        updated = await store.user_agents.set_password(OWNER, "new-hash")
        assert updated is not None and updated.hashed_password == "new-hash"
        reloaded = await store.user_agents.get(OWNER)
        assert reloaded is not None and reloaded.hashed_password == "new-hash"

        deleted = await store.user_agents.delete(OWNER)
        assert deleted is not None
        assert not await store.user_agents.exists(OWNER)


async def test_swarm_and_webhook_and_list_crud(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)

        swarm = MAILSwarm(
            name="chorus",
            description="d",
            keywords=["k"],
            agents=[],
            metadata={},
        )
        await store.swarms.add(swarm)
        assert await store.swarms.get("chorus") == swarm
        assert await store.swarms.list_all() == [swarm]

        webhook = MAILWebhook(
            webhook_id=f"wh_{_uuid()}",
            url="https://hooks.example.com/mail",
            events=["mail.delivered"],
            secret="shh",
        )
        await store.webhooks.add(webhook)
        assert await store.webhooks.get_by_id(webhook.webhook_id) == webhook
        assert await store.webhooks.get_by_url(webhook.url) == webhook

        mail_list = MAILListInBackend(
            **MAILList(
                name="team", swarm="chorus", host="localhost", owner=SENDER
            ).model_dump(),
            list_id=_uuid(),
            created_at=T1,
            updated_at=T1,
        )
        await store.lists.add(mail_list)
        # Member edit rewrites the JSON body wholesale, mirroring memory.
        mutated = mail_list.model_copy(
            update={"members": [OWNER], "updated_at": T2}
        )
        await store.lists.update(mutated)
        reloaded = await store.lists.get_by_address(mail_list.get_address())
        assert reloaded is not None and reloaded.members == [OWNER]


async def test_message_buffer_is_fifo_and_drains(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        ids = [_uuid() for _ in range(3)]
        for message_id in ids:
            await store.buffer.enqueue(message_id)

        assert await store.buffer.list_ids() == ids
        assert await store.buffer.drain() == ids
        # Buffer is empty after draining.
        assert await store.buffer.list_ids() == []
        assert await store.buffer.drain() == []


async def test_draft_entry_crud(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        draft_id = _uuid()
        entry = MAILDraftsEntry(
            draft=MAILDraft(
                draft_id=draft_id,
                subject="s",
                body="b",
                created_at=T1,
                updated_at=None,
            ),
            sent_at=None,
            sent_by=None,
        )
        await store.boxes.upsert_draft_entry(entry)
        assert await store.boxes.get_draft_entry(draft_id) == entry

        await store.boxes.delete_draft_entry(draft_id)
        assert await store.boxes.get_draft_entry(draft_id) is None


async def test_trash_summary_listing(db: Database) -> None:
    async with db.session() as session:
        store = MailStore(session)
        await store.user_agents.add(_agent())
        message_id = _uuid()
        await store.messages.add(_message(message_id, T1))
        await store.boxes.upsert_trash_entry(
            MAILTrashEntry(message=_message(message_id, T1), trashed_at=T2)
        )
        await store.boxes.add_membership(OWNER, BOX_TRASH, message_id, T2)

        page, total = await store.boxes.list_trash(OWNER, BoxFilterParams())

        assert total == 1
        assert page[0].message_id == message_id
        assert page[0].trashed_at == T2
