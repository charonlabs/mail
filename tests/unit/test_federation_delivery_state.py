# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Behavioral parity tests for Phase 2 durable federation state."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
)
from mail_protocol.network.requests import (
    AdminUserPostRequest,
    BoxFilterParams,
    DaemonDeliverLocalRequest,
    DraftPostRequest,
    DraftSendPostRequest,
)
from mail_server.backends.base import MAILServerBackend
from mail_server.backends.memory.api import MemoryBackend
from mail_server.backends.sqlite.api import SQLiteBackend
from mail_server.backends.sqlite.repositories import FederationOutboundRepository
from mail_server.backends.sqlite.schema import (
    FederationOutboundRow,
    MessageDeliveryTargetRow,
    MessageRow,
)
from mail_server.federation.records import BounceEmission, InboundFederationReceipt
from sqlalchemy import func, select

LOCAL_HOST = "local.example"
REMOTE_A = "remote-a.example"
REMOTE_B = "remote-b.example"
ADMIN = MAILAdmin(ua_type="admin", admin_id="root", host=LOCAL_HOST)
ALICE = MAILUserAgent(
    user_agent=MAILUser(ua_type="user", user_id="alice", host=LOCAL_HOST)
)
DAEMON = MAILDaemon(ua_type="daemon", worker_name="worker", host=LOCAL_HOST)


@pytest.fixture(params=("memory", "sqlite"))
async def federation_backend(
    request: pytest.FixtureRequest,
    deployment_dir: Path,
    tmp_path: Path,
) -> AsyncIterator[MAILServerBackend]:
    if request.param == "memory":
        backend: MAILServerBackend = MemoryBackend()
    else:
        backend = SQLiteBackend(f"sqlite:///{tmp_path / 'mail.db'}")
    await backend.on_server_startup(host=LOCAL_HOST)
    await backend.admin_post_user(
        ADMIN,
        AdminUserPostRequest(user_id="alice", user_password="pw"),
    )
    yield backend
    await backend.on_server_shutdown()


async def send(
    backend: MAILServerBackend,
    recipients: list[str],
) -> MAILMessage:
    draft = await backend.post_draft(
        ALICE,
        DraftPostRequest(subject="Federation state", body="durable body"),
    )
    return await backend.send_draft(
        ALICE,
        draft.draft.draft_id,
        DraftSendPostRequest(recipients=recipients),
    )


async def test_mixed_send_splits_targets_and_aggregates_completion(
    federation_backend: MAILServerBackend,
) -> None:
    recipients = [
        f"user:alice@{LOCAL_HOST}",
        f"bob@swarm@{REMOTE_A}",
        f"user:carol@{REMOTE_A}",
        f"dave@swarm@{REMOTE_B}",
    ]
    message = await send(federation_backend, recipients)

    targets = await federation_backend.get_message_delivery_targets(message.message_id)
    by_host = {target.destination_host: target for target in targets}
    assert set(by_host) == {LOCAL_HOST, REMOTE_A, REMOTE_B}
    assert by_host[LOCAL_HOST].kind == "local"
    assert by_host[REMOTE_A].recipients == recipients[1:3]

    outbound = await federation_backend.get_outbound_federation_deliveries(
        message.message_id
    )
    assert len(outbound) == 2
    assert len({delivery.envelope_id for delivery in outbound}) == 2
    assert all(
        delivery.envelope.message.message_id == message.message_id
        for delivery in outbound
    )
    assert {
        delivery.destination_host: delivery.envelope.message.recipients
        for delivery in outbound
    } == {REMOTE_A: recipients[1:3], REMOTE_B: recipients[3:]}

    assert await federation_backend.daemon_clear_message_buffer(DAEMON) == [
        message.message_id
    ]
    assert await federation_backend.daemon_clear_message_buffer(DAEMON) == []
    await federation_backend.daemon_deliver_local(
        DAEMON,
        DaemonDeliverLocalRequest(message_ids=[message.message_id]),
    )
    assert (
        await federation_backend.get_outbox_message(ALICE, message.message_id)
    ).delivered_at is None

    claimed = await federation_backend.claim_due_federation_deliveries(
        now=message.sent_at,
        lease_owner="worker-1",
        lease_duration=timedelta(minutes=1),
        limit=10,
    )
    assert len(claimed) == 2
    first_completed = await federation_backend.complete_federation_delivery(
        claimed[0].envelope_id,
        lease_owner="worker-1",
        completed_at=message.sent_at + timedelta(seconds=1),
    )
    assert first_completed.attempt_count == 1
    assert (
        await federation_backend.get_outbox_message(ALICE, message.message_id)
    ).delivered_at is None
    completed_at = message.sent_at + timedelta(seconds=2)
    await federation_backend.complete_federation_delivery(
        claimed[1].envelope_id,
        lease_owner="worker-1",
        completed_at=completed_at,
        delivered_by=f"daemon:federation@{LOCAL_HOST}",
    )
    assert (
        await federation_backend.get_outbox_message(ALICE, message.message_id)
    ).delivered_at == completed_at


async def test_remote_only_send_does_not_enter_local_buffer(
    federation_backend: MAILServerBackend,
) -> None:
    message = await send(federation_backend, [f"bob@swarm@{REMOTE_A}"])

    assert await federation_backend.daemon_clear_message_buffer(DAEMON) == []
    targets = await federation_backend.get_message_delivery_targets(message.message_id)
    assert [(target.kind, target.destination_host) for target in targets] == [
        ("remote", REMOTE_A)
    ]


async def test_remote_list_rejection_is_atomic(
    federation_backend: MAILServerBackend,
) -> None:
    draft = await federation_backend.post_draft(
        ALICE,
        DraftPostRequest(subject="No remote lists", body="body"),
    )

    with pytest.raises(ValueError, match="mailing-list"):
        await federation_backend.send_draft(
            ALICE,
            draft.draft.draft_id,
            DraftSendPostRequest(recipients=[f"list:all@swarm@{REMOTE_A}"]),
        )

    _, total = await federation_backend.get_outbox(ALICE, BoxFilterParams())
    assert total == 0
    assert await federation_backend.daemon_clear_message_buffer(DAEMON) == []
    assert (
        await federation_backend.get_draft(ALICE, draft.draft.draft_id)
    ).draft == draft.draft


async def test_retry_state_and_expired_lease_recovery(
    federation_backend: MAILServerBackend,
) -> None:
    message = await send(federation_backend, [f"bob@swarm@{REMOTE_A}"])
    first = (
        await federation_backend.claim_due_federation_deliveries(
            now=message.sent_at,
            lease_owner="worker-1",
            lease_duration=timedelta(seconds=10),
            limit=1,
        )
    )[0]
    assert (
        await federation_backend.claim_due_federation_deliveries(
            now=message.sent_at + timedelta(seconds=9),
            lease_owner="worker-2",
            lease_duration=timedelta(seconds=10),
            limit=1,
        )
        == []
    )
    with pytest.raises(ValueError, match="not leased"):
        await federation_backend.record_federation_attempt(
            first.envelope_id,
            lease_owner="worker-1",
            attempted_at=message.sent_at + timedelta(seconds=11),
            next_attempt_at=message.sent_at + timedelta(seconds=40),
        )

    recovered = (
        await federation_backend.claim_due_federation_deliveries(
            now=message.sent_at + timedelta(seconds=10),
            lease_owner="worker-2",
            lease_duration=timedelta(seconds=10),
            limit=1,
        )
    )[0]
    assert recovered.envelope_id == first.envelope_id
    next_attempt = message.sent_at + timedelta(seconds=40)
    recorded = await federation_backend.record_federation_attempt(
        recovered.envelope_id,
        lease_owner="worker-2",
        attempted_at=message.sent_at + timedelta(seconds=11),
        next_attempt_at=next_attempt,
        http_status=503,
        error="temporarily unavailable",
    )
    assert recorded.status == "pending"
    assert recorded.attempt_count == 1
    assert recorded.attempt_timestamps == [message.sent_at + timedelta(seconds=11)]

    final_claim = (
        await federation_backend.claim_due_federation_deliveries(
            now=next_attempt,
            lease_owner="worker-3",
            lease_duration=timedelta(seconds=10),
            limit=1,
        )
    )[0]
    failed = await federation_backend.fail_federation_delivery(
        final_claim.envelope_id,
        lease_owner="worker-3",
        completed_at=next_attempt + timedelta(seconds=1),
        failure_code="host_rejected",
        http_status=403,
        error="peer rejected delivery",
    )
    assert failed.status == "dead_letter"
    assert failed.attempt_count == 2
    target = (
        await federation_backend.get_message_delivery_targets(message.message_id)
    )[0]
    assert target.status == "failed"
    assert target.failure_code == "host_rejected"
    assert (
        await federation_backend.get_outbox_message(ALICE, message.message_id)
    ).delivered_at is None


def inbound_message(*, body: str = "remote body") -> MAILMessage:
    now = datetime.now(UTC).replace(microsecond=0)
    return MAILMessage(
        mail_version="2.0",
        message_id="55555555-5555-4555-8555-555555555555",
        sender=f"user:bob@{REMOTE_A}",
        recipients=[f"user:alice@{LOCAL_HOST}"],
        subject="Inbound",
        body=body,
        tags=[],
        sent_at=now,
        metadata={},
    )


def receipt(
    message: MAILMessage,
    *,
    envelope_id: str = "77777777-7777-4777-8777-777777777777",
) -> InboundFederationReceipt:
    now = datetime.now(UTC).replace(microsecond=0)
    return InboundFederationReceipt(
        envelope_id=envelope_id,
        sender_host=REMOTE_A,
        inner_message_id=message.message_id,
        content_hash="a" * 64,
        accepted_at=now,
        expires_at=now + timedelta(hours=24),
    )


async def test_inbound_acceptance_is_atomic_and_deduplicated(
    federation_backend: MAILServerBackend,
) -> None:
    message = inbound_message()
    replay_record = receipt(message)

    assert await federation_backend.accept_inbound_federation(replay_record, message)
    assert not await federation_backend.accept_inbound_federation(
        replay_record, message
    )
    assert await federation_backend.daemon_clear_message_buffer(DAEMON) == [
        message.message_id
    ]
    assert await federation_backend.daemon_clear_message_buffer(DAEMON) == []

    collision_receipt = receipt(
        message,
        envelope_id="88888888-8888-4888-8888-888888888888",
    )
    with pytest.raises(ValueError, match="collides"):
        await federation_backend.accept_inbound_federation(
            collision_receipt,
            inbound_message(body="attacker replacement"),
        )
    # The failed collision did not reserve its envelope ID.
    assert await federation_backend.accept_inbound_federation(
        collision_receipt, message
    )


async def test_receipt_expiry_and_bounce_counts(
    federation_backend: MAILServerBackend,
) -> None:
    message = inbound_message()
    replay_record = receipt(message)
    assert await federation_backend.accept_inbound_federation(replay_record, message)
    assert (
        await federation_backend.purge_expired_federation_receipts(
            now=replay_record.expires_at
        )
        == 1
    )

    emitted_at = datetime.now(UTC).replace(microsecond=0)
    emitted = BounceEmission(
        emission_id="99999999-9999-4999-8999-999999999999",
        original_sender=f"user:alice@{LOCAL_HOST}",
        original_message_id="66666666-6666-4666-8666-666666666666",
        failed_recipient=f"bob@swarm@{REMOTE_A}",
        emitted_at=emitted_at,
        outcome="emitted",
    )
    suppressed = emitted.model_copy(
        update={
            "emission_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "outcome": "suppressed",
        }
    )
    await federation_backend.record_bounce_emission(emitted)
    await federation_backend.record_bounce_emission(suppressed)
    assert (
        await federation_backend.count_bounce_emissions_since(
            emitted.original_sender,
            since=emitted_at - timedelta(seconds=1),
        )
        == 1
    )


async def test_sqlite_restart_preserves_envelope_and_attempt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "restart.db"
    backend = SQLiteBackend(f"sqlite:///{database}")
    await backend.on_server_startup(host=LOCAL_HOST)
    await backend.admin_post_user(
        ADMIN,
        AdminUserPostRequest(user_id="alice", user_password="pw"),
    )
    message = await send(backend, [f"bob@swarm@{REMOTE_A}"])
    claimed = (
        await backend.claim_due_federation_deliveries(
            now=message.sent_at,
            lease_owner="worker",
            lease_duration=timedelta(seconds=30),
            limit=1,
        )
    )[0]
    recorded = await backend.record_federation_attempt(
        claimed.envelope_id,
        lease_owner="worker",
        attempted_at=message.sent_at + timedelta(seconds=1),
        next_attempt_at=message.sent_at + timedelta(seconds=30),
        error="network",
    )
    await backend.on_server_shutdown()

    reopened = SQLiteBackend(f"sqlite:///{database}")
    await reopened.on_server_startup(host=LOCAL_HOST)
    try:
        restored = (
            await reopened.get_outbound_federation_deliveries(message.message_id)
        )[0]
        assert restored.envelope_id == recorded.envelope_id
        assert restored.attempt_count == 1
        assert restored.next_attempt_at == recorded.next_attempt_at
    finally:
        await reopened.on_server_shutdown()


async def test_sqlite_remote_plan_rolls_back_if_envelope_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SQLiteBackend(f"sqlite:///{tmp_path / 'rollback.db'}")
    await backend.on_server_startup(host=LOCAL_HOST)
    await backend.admin_post_user(
        ADMIN,
        AdminUserPostRequest(user_id="alice", user_password="pw"),
    )
    draft = await backend.post_draft(
        ALICE,
        DraftPostRequest(subject="Rollback", body="all or nothing"),
    )

    async def fail_add(
        _repository: FederationOutboundRepository,
        _delivery: object,
    ) -> None:
        raise RuntimeError("outbound write failed")

    monkeypatch.setattr(FederationOutboundRepository, "add", fail_add)
    with pytest.raises(RuntimeError, match="outbound write failed"):
        await backend.send_draft(
            ALICE,
            draft.draft.draft_id,
            DraftSendPostRequest(recipients=[f"bob@swarm@{REMOTE_A}"]),
        )

    async with backend._db.session() as session:
        for row_type in (MessageRow, MessageDeliveryTargetRow, FederationOutboundRow):
            count = await session.scalar(select(func.count()).select_from(row_type))
            assert count == 0
    _, outbox_count = await backend.get_outbox(ALICE, BoxFilterParams())
    assert outbox_count == 0
    await backend.on_server_shutdown()


async def test_memory_restart_preserves_envelope_and_attempt(
    deployment_dir: Path,
) -> None:
    backend = MemoryBackend()
    await backend.on_server_startup(host=LOCAL_HOST)
    await backend.admin_post_user(
        ADMIN,
        AdminUserPostRequest(user_id="alice", user_password="pw"),
    )
    message = await send(backend, [f"bob@swarm@{REMOTE_A}"])
    claimed = (
        await backend.claim_due_federation_deliveries(
            now=message.sent_at,
            lease_owner="worker",
            lease_duration=timedelta(seconds=30),
            limit=1,
        )
    )[0]
    recorded = await backend.record_federation_attempt(
        claimed.envelope_id,
        lease_owner="worker",
        attempted_at=message.sent_at + timedelta(seconds=1),
        next_attempt_at=message.sent_at + timedelta(seconds=30),
        error="network",
    )
    inbound = inbound_message()
    inbound_receipt = receipt(inbound)
    assert await backend.accept_inbound_federation(inbound_receipt, inbound)
    bounce = BounceEmission(
        emission_id="99999999-9999-4999-8999-999999999999",
        original_sender=f"user:alice@{LOCAL_HOST}",
        original_message_id=message.message_id,
        failed_recipient=f"bob@swarm@{REMOTE_A}",
        emitted_at=message.sent_at,
        outcome="emitted",
    )
    await backend.record_bounce_emission(bounce)
    await backend.on_server_shutdown()

    reopened = MemoryBackend()
    await reopened.on_server_startup(host=LOCAL_HOST)
    try:
        restored = (
            await reopened.get_outbound_federation_deliveries(message.message_id)
        )[0]
        assert restored.envelope_id == recorded.envelope_id
        assert restored.attempt_count == 1
        assert restored.next_attempt_at == recorded.next_attempt_at
        assert not await reopened.accept_inbound_federation(inbound_receipt, inbound)
        assert (
            await reopened.count_bounce_emissions_since(
                bounce.original_sender,
                since=bounce.emitted_at,
            )
            == 1
        )
    finally:
        await reopened.on_server_shutdown()
