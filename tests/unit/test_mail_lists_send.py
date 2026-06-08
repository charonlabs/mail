# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

# mail_server.auth checks MAIL_JWT_* env vars at import time. The
# values are inert for these tests; set placeholders before any
# mail_server.* import so collection succeeds.
os.environ.setdefault("MAIL_JWT_SECRET_KEY", "test-secret-not-used")
os.environ.setdefault("MAIL_JWT_ALGORITHM", "HS256")

import pytest
from mail_protocol.core.lists import MAILListInBackend, MAILListPolicy
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.user_agents import (
    MAILAgent,
    MAILUserAgentInBackend,
)
from mail_protocol.network.requests import DaemonDeliverLocalRequest
from mail_server.auth import get_password_hash  # noqa: E402
from mail_server.backends.memory import fs as memory_fs  # noqa: E402
from mail_server.backends.memory.api import MemoryBackend  # noqa: E402

HOST = "localhost"
SWARM = "chorus"
SENDER = f"sender@{SWARM}@{HOST}"
ALICE = f"alice@{SWARM}@{HOST}"
BOB = f"bob@{SWARM}@{HOST}"
LIST_ADDRESS = f"list:welfare-discourse@{SWARM}@{HOST}"


@pytest.fixture
def deployment_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    deployment = tmp_path / "deployment"
    for subdir in (
        "user_agents",
        "swarms",
        "messages",
        "inbox_entries",
        "inboxes",
        "outbox_entries",
        "outboxes",
        "draft_entries",
        "drafts",
        "trash_entries",
        "trashes",
        "webhooks",
        "lists",
    ):
        (deployment / subdir).mkdir(parents=True, exist_ok=True)
    (deployment / "message_buffer.lock").touch()
    monkeypatch.setattr(memory_fs, "DEPLOYMENT_PATH", deployment)
    return deployment


def _agent(name: str) -> MAILUserAgentInBackend:
    return MAILUserAgentInBackend(
        user_agent=MAILAgent(
            ua_type="agent",
            name=name,
            swarm=SWARM,
            host=HOST,
        ),
        hashed_password=get_password_hash("placeholder"),
    )


def _seed_list(
    backend: MemoryBackend,
    members: list[str],
) -> MAILListInBackend:
    now = datetime(2026, 6, 6, tzinfo=UTC)
    record = MAILListInBackend(
        name="welfare-discourse",
        swarm=SWARM,
        host=HOST,
        owner="admin:ryan@localhost",
        members=members,
        policy=MAILListPolicy(),
        list_id="11111111-1111-1111-1111-111111111111",
        created_at=now,
        updated_at=now,
    )
    backend.lists[record.get_address()] = record
    return record


def _seed_message(
    backend: MemoryBackend,
    *,
    recipients: list[str],
) -> MAILMessage:
    now = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    message = MAILMessage(
        message_id="22222222-2222-2222-2222-222222222222",
        sender=SENDER,
        recipients=recipients,
        subject="Daily briefing",
        body="Body text.",
        sent_at=now,
        metadata={},
    )
    backend.messages[message.message_id] = message
    backend.outbox_entries[message.message_id] = MAILOutboxEntrySummary(
        message_id=message.message_id,
        sender=SENDER,
        recipients=recipients,
        subject=message.subject,
        body_size=len(message.body),
        sent_at=now,
        delivered_at=None,
        delivered_by=None,
    )
    return message


@pytest.fixture
async def backend(deployment_dir: Path) -> MemoryBackend:
    instance = MemoryBackend()
    await instance.on_server_startup(host=HOST)

    # Populate a swarm and four agents so the recipient-address lookup
    # in ``_deliver_to_address`` resolves to real user-agents.
    instance.swarms[SWARM] = MAILSwarm(
        name=SWARM,
        description="test swarm",
        keywords=[],
        agents=[],
        metadata={},
    )
    for name, address in (
        ("sender", SENDER),
        ("alice", ALICE),
        ("bob", BOB),
    ):
        instance.user_agents[address] = _agent(name)
        instance.inboxes[address] = []
        instance.outboxes[address] = []
        instance.drafts[address] = []
        instance.trashes[address] = []
    return instance


def _daemon() -> Any:
    from mail_protocol.core.user_agents import MAILDaemon

    return MAILDaemon(
        ua_type="daemon",
        worker_name="dummy",
        host=HOST,
    )


@pytest.mark.asyncio
async def test_send_to_list_expands_to_each_member(
    backend: MemoryBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_list(backend, members=[ALICE, BOB])
    message = _seed_message(backend, recipients=[LIST_ADDRESS])

    # Stub out the webhook firing so the test focuses on inbox state.
    monkeypatch.setattr(
        backend,
        "_handle_webhook_delivered",
        AsyncMock(),
    )

    await backend.daemon_deliver_local(
        daemon=_daemon(),
        payload=DaemonDeliverLocalRequest(message_ids=[message.message_id]),
    )

    assert backend.inboxes[ALICE] == [message.message_id]
    assert backend.inboxes[BOB] == [message.message_id]
    # The original recipients[] on the message is preserved.
    assert backend.messages[message.message_id].recipients == [LIST_ADDRESS]


@pytest.mark.asyncio
async def test_send_to_list_fires_webhook_with_list_address(
    backend: MemoryBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_list(backend, members=[ALICE])
    message = _seed_message(backend, recipients=[LIST_ADDRESS])

    handler = AsyncMock()
    monkeypatch.setattr(backend, "_handle_webhook_delivered", handler)

    await backend.daemon_deliver_local(
        daemon=_daemon(),
        payload=DaemonDeliverLocalRequest(message_ids=[message.message_id]),
    )

    handler.assert_awaited_once()
    call = handler.await_args
    assert call.kwargs["recipient"] == ALICE
    assert call.kwargs["list_address"] == LIST_ADDRESS


@pytest.mark.asyncio
async def test_direct_recipient_fires_webhook_without_list_address(
    backend: MemoryBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _seed_message(backend, recipients=[ALICE])

    handler = AsyncMock()
    monkeypatch.setattr(backend, "_handle_webhook_delivered", handler)

    await backend.daemon_deliver_local(
        daemon=_daemon(),
        payload=DaemonDeliverLocalRequest(message_ids=[message.message_id]),
    )

    handler.assert_awaited_once()
    call = handler.await_args
    assert call.kwargs["recipient"] == ALICE
    assert call.kwargs["list_address"] is None


@pytest.mark.asyncio
async def test_unknown_list_is_skipped_silently(
    backend: MemoryBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No list seeded; the recipient references a missing list.
    message = _seed_message(backend, recipients=[LIST_ADDRESS, ALICE])

    handler = AsyncMock()
    monkeypatch.setattr(backend, "_handle_webhook_delivered", handler)

    await backend.daemon_deliver_local(
        daemon=_daemon(),
        payload=DaemonDeliverLocalRequest(message_ids=[message.message_id]),
    )

    # The direct recipient still got the message; the missing list
    # didn't poison the rest of the delivery.
    assert backend.inboxes[ALICE] == [message.message_id]
    assert handler.await_count == 1
    assert handler.await_args.kwargs["recipient"] == ALICE


@pytest.mark.asyncio
async def test_nested_list_members_are_skipped(
    backend: MemoryBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A list whose members include another list address.
    nested = f"list:other@{SWARM}@{HOST}"
    _seed_list(backend, members=[ALICE, nested])
    message = _seed_message(backend, recipients=[LIST_ADDRESS])

    handler = AsyncMock()
    monkeypatch.setattr(backend, "_handle_webhook_delivered", handler)

    await backend.daemon_deliver_local(
        daemon=_daemon(),
        payload=DaemonDeliverLocalRequest(message_ids=[message.message_id]),
    )

    # alice got it; the nested list address was skipped, not recursed.
    assert backend.inboxes[ALICE] == [message.message_id]
    assert handler.await_count == 1
    assert handler.await_args.kwargs["recipient"] == ALICE
    assert handler.await_args.kwargs["list_address"] == LIST_ADDRESS


@pytest.mark.asyncio
async def test_mixed_list_and_direct_recipients(
    backend: MemoryBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_list(backend, members=[ALICE])
    message = _seed_message(backend, recipients=[LIST_ADDRESS, BOB])

    handler = AsyncMock()
    monkeypatch.setattr(backend, "_handle_webhook_delivered", handler)

    await backend.daemon_deliver_local(
        daemon=_daemon(),
        payload=DaemonDeliverLocalRequest(message_ids=[message.message_id]),
    )

    # alice received via list; bob received directly.
    assert backend.inboxes[ALICE] == [message.message_id]
    assert backend.inboxes[BOB] == [message.message_id]

    assert handler.await_count == 2
    list_kwargs = [
        c.kwargs for c in handler.await_args_list if c.kwargs["recipient"] == ALICE
    ]
    direct_kwargs = [
        c.kwargs for c in handler.await_args_list if c.kwargs["recipient"] == BOB
    ]
    assert list_kwargs and list_kwargs[0]["list_address"] == LIST_ADDRESS
    assert direct_kwargs and direct_kwargs[0]["list_address"] is None
