# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Direct end-to-end coverage for ``SQLiteBackend``, exercised through the public
protocol methods against a real temp-file database.

Emphasis on the gap-fill methods the memory backend leaves as
``NotImplementedError`` (``delete_inbox_message``, ``delete_draft``,
``delete_trash_message``, ``clear_trash``, ``admin_webhook_patch``,
``daemon_deliver_remote``), since the shared integration suite cannot reach
them — their HTTP routes are still router-level stubs.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mail_protocol.core.lists import MAILListPolicy
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
)
from mail_protocol.network.requests import (
    AdminAgentPostRequest,
    AdminDaemonPostRequest,
    AdminListPatchRequest,
    AdminListPostRequest,
    AdminSwarmPostRequest,
    AdminUserPostRequest,
    AdminWebhooksPatchRequest,
    AdminWebhooksPostRequest,
    AuthPasswordResetRequest,
    BoxFilterParams,
    DaemonDeliverLocalRequest,
    DaemonDeliverRemoteRequest,
    DraftPatchRequest,
    DraftPostRequest,
    DraftSendPostRequest,
)
from mail_server.backends.sqlite.api import SQLiteBackend

ADMIN = MAILAdmin(ua_type="admin", admin_id="ryan", host="localhost")
DAEMON = MAILDaemon(ua_type="daemon", worker_name="dummy", host="localhost")
ALICE = MAILUserAgent(
    user_agent=MAILUser(ua_type="user", user_id="alice", host="localhost")
)
SAGE = MAILUserAgent(
    user_agent=MAILAgent(
        ua_type="agent", name="sage", swarm="chorus", host="localhost"
    )
)
SAGE_ADDR = "sage@chorus@localhost"


@pytest.fixture
async def backend(tmp_path: Path) -> AsyncIterator[SQLiteBackend]:
    be = SQLiteBackend(f"sqlite:///{tmp_path / 'mail.db'}")
    await be.on_server_startup(host="localhost")
    # A cast of one user (sender) and one agent (recipient).
    await be.admin_post_user(
        ADMIN, AdminUserPostRequest(user_id="alice", user_password="pw")
    )
    await be.admin_post_agent(
        ADMIN,
        AdminAgentPostRequest(
            agent_name="sage", swarm_name="chorus", agent_password="pw"
        ),
    )
    await be.admin_post_daemon(
        ADMIN, AdminDaemonPostRequest(worker_name="dummy", daemon_password="pw")
    )
    yield be
    await be.on_server_shutdown()


async def _send(backend: SQLiteBackend, recipients: list[str]) -> str:
    """Alice drafts and sends a message; return its message id."""

    entry = await backend.post_draft(
        ALICE, DraftPostRequest(subject="Hi", body="hello there")
    )
    message = await backend.send_draft(
        ALICE,
        entry.draft.draft_id,
        DraftSendPostRequest(recipients=recipients),
    )
    return message.message_id


# --------------------------------------------------------------------------- #
# Admin CRUD + lifecycle
# --------------------------------------------------------------------------- #


async def test_admin_agent_crud_and_duplicates(backend: SQLiteBackend) -> None:
    assert await backend.admin_get_agents(ADMIN) == ["sage@chorus"]
    assert (await backend.admin_get_agent(ADMIN, "sage@chorus")).name == "sage"

    with pytest.raises(ValueError, match="already taken"):
        await backend.admin_post_agent(
            ADMIN,
            AdminAgentPostRequest(
                agent_name="sage", swarm_name="chorus", agent_password="pw"
            ),
        )

    deleted = await backend.admin_delete_agent(ADMIN, "sage@chorus")
    assert deleted.name == "sage"
    assert await backend.admin_get_agents(ADMIN) == []


async def test_reset_password(backend: SQLiteBackend) -> None:
    assert await backend.user_agent_exists("user:alice@localhost")
    result = await backend.reset_password(
        ALICE.user_agent,
        AuthPasswordResetRequest(current_password="pw", new_password="pw2"),
    )
    assert result == "success"
    with pytest.raises(ValueError, match="incorrect password"):
        await backend.reset_password(
            ALICE.user_agent,
            AuthPasswordResetRequest(current_password="wrong", new_password="pw3"),
        )


# --------------------------------------------------------------------------- #
# Draft -> send -> deliver -> inbox lifecycle
# --------------------------------------------------------------------------- #


async def test_full_local_delivery_lifecycle(backend: SQLiteBackend) -> None:
    message_id = await _send(backend, [SAGE_ADDR])

    # The send lands in alice's outbox and the delivery buffer.
    outbox, total = await backend.get_outbox(ALICE, BoxFilterParams())
    assert total == 1 and outbox[0].message_id == message_id

    buffered = await backend.daemon_clear_message_buffer(DAEMON)
    assert buffered == [message_id]
    # Buffer is drained; a second clear is empty.
    assert await backend.daemon_clear_message_buffer(DAEMON) == []

    delivered = await backend.daemon_deliver_local(
        DAEMON, DaemonDeliverLocalRequest(message_ids=[message_id])
    )
    assert [m.message_id for m in delivered] == [message_id]

    # The agent recipient now has it in their inbox.
    inbox, total = await backend.get_inbox(SAGE, BoxFilterParams())
    assert total == 1 and inbox[0].message_id == message_id
    full = await backend.get_inbox_message(SAGE, message_id)
    assert full.message.body == "hello there"
    assert full.delivered_by == DAEMON.get_address()

    # The sender's outbox entry is marked delivered.
    out_msg = await backend.get_outbox_message(ALICE, message_id)
    assert out_msg.delivered_at is not None


async def test_draft_patch_and_delete(backend: SQLiteBackend) -> None:
    entry = await backend.post_draft(
        ALICE, DraftPostRequest(subject="Draft", body="body")
    )
    draft_id = entry.draft.draft_id

    patched = await backend.patch_draft(
        ALICE, draft_id, DraftPatchRequest(subject="Edited")
    )
    assert patched.draft.subject == "Edited"
    assert patched.draft.updated_at is not None

    deleted = await backend.delete_draft(ALICE, draft_id)
    assert deleted.draft.draft_id == draft_id
    with pytest.raises(ValueError, match="not found in draft box"):
        await backend.get_draft(ALICE, draft_id)


# --------------------------------------------------------------------------- #
# Gap-fill: inbox -> trash move, trash delete, clear
# --------------------------------------------------------------------------- #


async def test_delete_inbox_message_moves_to_trash(backend: SQLiteBackend) -> None:
    message_id = await _send(backend, [SAGE_ADDR])
    await backend.daemon_deliver_local(
        DAEMON, DaemonDeliverLocalRequest(message_ids=[message_id])
    )

    moved = await backend.delete_inbox_message(SAGE, message_id)
    assert moved.message.message_id == message_id

    # Gone from inbox, present in trash.
    inbox, inbox_total = await backend.get_inbox(SAGE, BoxFilterParams())
    assert inbox_total == 0 and inbox == []
    trash, trash_total = await backend.get_trash(SAGE, BoxFilterParams())
    assert trash_total == 1 and trash[0].message_id == message_id

    fetched = await backend.get_trash_message(SAGE, message_id)
    assert fetched.message.message_id == message_id


async def test_delete_trash_message_and_clear(backend: SQLiteBackend) -> None:
    first = await _send(backend, [SAGE_ADDR])
    second = await _send(backend, [SAGE_ADDR])
    await backend.daemon_deliver_local(
        DAEMON, DaemonDeliverLocalRequest(message_ids=[first, second])
    )
    await backend.delete_inbox_message(SAGE, first)
    await backend.delete_inbox_message(SAGE, second)

    removed = await backend.delete_trash_message(SAGE, first)
    assert removed.message.message_id == first
    _, total = await backend.get_trash(SAGE, BoxFilterParams())
    assert total == 1

    cleared = await backend.clear_trash(SAGE)
    assert [s.message_id for s in cleared] == [second]
    _, total_after = await backend.get_trash(SAGE, BoxFilterParams())
    assert total_after == 0


# --------------------------------------------------------------------------- #
# Gap-fill: webhook patch + remote delivery
# --------------------------------------------------------------------------- #


async def test_webhook_crud_and_patch(backend: SQLiteBackend) -> None:
    created = await backend.admin_webhook_post(
        ADMIN,
        AdminWebhooksPostRequest(
            url="https://hooks.example.com/a",
            events=["mail.delivered"],
            secret="s1",
        ),
    )
    # Idempotent on URL.
    again = await backend.admin_webhook_post(
        ADMIN,
        AdminWebhooksPostRequest(
            url="https://hooks.example.com/a",
            events=["mail.delivered"],
            secret="ignored",
        ),
    )
    assert again.webhook_id == created.webhook_id

    patched = await backend.admin_webhook_patch(
        ADMIN,
        created.webhook_id,
        AdminWebhooksPatchRequest(url="https://hooks.example.com/b", secret="s2"),
    )
    assert patched.webhook_id == created.webhook_id  # id preserved across URL move
    assert patched.url == "https://hooks.example.com/b"
    assert patched.secret == "s2"

    # Refetch by id reflects the move; the old URL is gone.
    refetched = await backend.admin_webhook_get(ADMIN, created.webhook_id)
    assert refetched.url == "https://hooks.example.com/b"
    assert await backend.admin_webhooks_get(ADMIN) == [created.webhook_id]

    with pytest.raises(ValueError, match="not found"):
        await backend.admin_webhook_patch(
            ADMIN,
            "wh_missing",
            AdminWebhooksPatchRequest(url="https://x.example.com", secret="s"),
        )


async def test_daemon_deliver_remote(backend: SQLiteBackend) -> None:
    remote = MAILMessage(
        mail_version="2.0",
        message_id="99999999-9999-4999-8999-999999999999",
        sender="echo@otherswarm@remote.example.com",
        recipients=[SAGE_ADDR],
        subject="Remote",
        body="from afar",
        tags=[],
        sent_at=datetime.now(UTC),
        metadata={},
    )
    delivered = await backend.daemon_deliver_remote(
        DAEMON, DaemonDeliverRemoteRequest(messages=[remote])
    )
    assert [m.message_id for m in delivered] == [remote.message_id]

    inbox, total = await backend.get_inbox(SAGE, BoxFilterParams())
    assert total == 1 and inbox[0].message_id == remote.message_id
    # The remote message was persisted into the canonical store.
    assert (await backend.get_message(remote.message_id)).body == "from afar"


# --------------------------------------------------------------------------- #
# Swarms + lists
# --------------------------------------------------------------------------- #


async def test_swarm_and_list_crud(backend: SQLiteBackend) -> None:
    await backend.admin_post_swarm(
        ADMIN,
        AdminSwarmPostRequest(name="newswarm", description="d", keywords=["k"]),
    )
    assert (await backend.get_swarm("newswarm")).name == "newswarm"
    assert await backend.get_swarm_health("newswarm") == "ok"

    created = await backend.admin_post_list(
        ADMIN,
        AdminListPostRequest(
            name="team",
            swarm_name="chorus",
            owner="user:alice@localhost",
            members=[],
        ),
    )
    address = created.get_address()

    with_member = await backend.add_list_member(address, SAGE_ADDR)
    assert with_member.members == [SAGE_ADDR]
    # Idempotent re-add.
    assert (await backend.add_list_member(address, SAGE_ADDR)).members == [SAGE_ADDR]

    without = await backend.remove_list_member(address, SAGE_ADDR)
    assert without.members == []

    patched = await backend.admin_patch_list(
        ADMIN,
        address,
        AdminListPatchRequest(policy=MAILListPolicy(visibility="private")),
    )
    assert patched.policy.visibility == "private"

    await backend.admin_delete_list(ADMIN, address)
    with pytest.raises(ValueError, match="list not found"):
        await backend.get_list(address)
