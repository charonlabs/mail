# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Phase 5 local DSN delivery, deduplication, and no-amplification tests."""

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from mail_protocol.core.dsn import MAILDSN
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
)
from mail_protocol.network.requests import (
    AdminDaemonPostRequest,
    AdminUserPostRequest,
    DaemonDeliverLocalRequest,
    DraftPostRequest,
    DraftSendPostRequest,
)
from mail_server.backends.base import MAILServerBackend
from mail_server.backends.memory.api import MemoryBackend
from mail_server.backends.sqlite.api import SQLiteBackend
from mail_server.backends.sqlite.repositories import BounceEmissionRepository
from mail_server.federation.bounces import build_federation_bounces

LOCAL_HOST = "local.example"
ADMIN = MAILAdmin(ua_type="admin", admin_id="root", host=LOCAL_HOST)
ALICE = MAILUserAgent(
    user_agent=MAILUser(ua_type="user", user_id="alice", host=LOCAL_HOST)
)
DELIVERY_DAEMON = MAILDaemon(
    ua_type="daemon",
    worker_name="delivery",
    host=LOCAL_HOST,
)
BOUNCE_DAEMON = MAILDaemon(
    ua_type="daemon",
    worker_name="bounces",
    host=LOCAL_HOST,
    scopes=["bounce:emit"],
)
MISSING = f"user:missing@{LOCAL_HOST}"


@pytest.fixture(params=("memory", "sqlite"))
async def bounce_backend(
    request: pytest.FixtureRequest,
    deployment_dir: Path,
    tmp_path: Path,
) -> AsyncIterator[MAILServerBackend]:
    if request.param == "memory":
        backend: MAILServerBackend = MemoryBackend()
    else:
        backend = SQLiteBackend(f"sqlite:///{tmp_path / 'bounces.db'}")
    await backend.on_server_startup(host=LOCAL_HOST)
    await backend.admin_post_user(
        ADMIN,
        AdminUserPostRequest(user_id="alice", user_password="pw"),
    )
    await backend.admin_post_daemon(
        ADMIN,
        AdminDaemonPostRequest(
            worker_name="bounces",
            daemon_password="pw",
            scopes=["bounce:emit"],
        ),
    )
    await backend.configure_bounce_delivery(
        emitter=BOUNCE_DAEMON,
        rate_limit=100,
    )
    yield backend
    await backend.on_server_shutdown()


async def _send_local_failure(backend: MAILServerBackend):
    draft = await backend.post_draft(
        ALICE,
        DraftPostRequest(subject="Local failure", body="body"),
    )
    message = await backend.send_draft(
        ALICE,
        draft.draft.draft_id,
        DraftSendPostRequest(recipients=[ALICE.get_address(), MISSING]),
    )
    claimed = await backend.daemon_clear_message_buffer(DELIVERY_DAEMON)
    assert claimed == [message.message_id]
    await backend.daemon_deliver_local(
        DELIVERY_DAEMON,
        DaemonDeliverLocalRequest(message_ids=claimed),
    )
    return message


async def test_local_unknown_recipient_queues_one_attemptless_dsn(
    bounce_backend: MAILServerBackend,
) -> None:
    original = await _send_local_failure(bounce_backend)

    emissions = await bounce_backend.get_bounce_emissions(original.message_id)
    assert len(emissions) == 1
    assert emissions[0].outcome == "emitted"
    assert emissions[0].dsn_message_id is not None
    dsn_message = await bounce_backend.get_message(emissions[0].dsn_message_id)
    dsn = MAILDSN.model_validate(dsn_message.metadata["dsn"])
    assert dsn.failure_code == "recipient_not_found"
    assert dsn.failed_recipient == MISSING
    assert dsn.failed_at == "origin"
    assert dsn.attempt_count is None
    assert dsn.attempt_timestamps is None

    # A replayed local-delivery call cannot reserve or queue a second DSN.
    await bounce_backend.daemon_deliver_local(
        DELIVERY_DAEMON,
        DaemonDeliverLocalRequest(message_ids=[original.message_id]),
    )
    assert len(await bounce_backend.get_bounce_emissions(original.message_id)) == 1

    original_target = (
        await bounce_backend.get_message_delivery_targets(original.message_id)
    )[0]
    assert original_target.status == "failed"
    assert original_target.failure_code == "recipient_not_found"
    assert (
        await bounce_backend.get_outbox_message(ALICE, original.message_id)
    ).delivered_at is None

    dsn_ids = await bounce_backend.daemon_clear_message_buffer(DELIVERY_DAEMON)
    assert dsn_ids == [dsn_message.message_id]
    await bounce_backend.daemon_deliver_local(
        DELIVERY_DAEMON,
        DaemonDeliverLocalRequest(message_ids=dsn_ids),
    )
    dsn_target = (
        await bounce_backend.get_message_delivery_targets(dsn_message.message_id)
    )[0]
    assert dsn_target.status == "succeeded"


async def test_failed_bounce_delivery_is_recorded_without_chaining(
    bounce_backend: MAILServerBackend,
) -> None:
    original = await _send_local_failure(bounce_backend)
    emission = (await bounce_backend.get_bounce_emissions(original.message_id))[0]
    assert emission.dsn_message_id is not None
    dsn_ids = await bounce_backend.daemon_clear_message_buffer(DELIVERY_DAEMON)
    await bounce_backend.admin_delete_user(ADMIN, "alice")

    await bounce_backend.daemon_deliver_local(
        DELIVERY_DAEMON,
        DaemonDeliverLocalRequest(message_ids=dsn_ids),
    )

    updated = (await bounce_backend.get_bounce_emissions(original.message_id))[0]
    assert updated.outcome == "failed"
    assert len(await bounce_backend.get_bounce_emissions(original.message_id)) == 1
    assert await bounce_backend.daemon_clear_message_buffer(DELIVERY_DAEMON) == []


async def test_sqlite_restart_preserves_reserved_dsn_once(tmp_path: Path) -> None:
    path = tmp_path / "restart-bounce.db"
    backend = SQLiteBackend(f"sqlite:///{path}")
    await backend.on_server_startup(host=LOCAL_HOST)
    await backend.admin_post_user(
        ADMIN,
        AdminUserPostRequest(user_id="alice", user_password="pw"),
    )
    await backend.admin_post_daemon(
        ADMIN,
        AdminDaemonPostRequest(
            worker_name="bounces",
            daemon_password="pw",
            scopes=["bounce:emit"],
        ),
    )
    await backend.configure_bounce_delivery(emitter=BOUNCE_DAEMON, rate_limit=100)
    original = await _send_local_failure(backend)
    reserved = (await backend.get_bounce_emissions(original.message_id))[0]
    await backend.on_server_shutdown()

    reopened = SQLiteBackend(f"sqlite:///{path}")
    await reopened.on_server_startup(host=LOCAL_HOST)
    try:
        emissions = await reopened.get_bounce_emissions(original.message_id)
        assert emissions == [reserved]
        assert reserved.dsn_message_id is not None
        assert (await reopened.get_message(reserved.dsn_message_id)).metadata["dsn"]
        assert await reopened.daemon_clear_message_buffer(DELIVERY_DAEMON) == [
            reserved.dsn_message_id
        ]
    finally:
        await reopened.on_server_shutdown()


async def test_sqlite_terminal_failure_and_bounce_reservation_are_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SQLiteBackend(f"sqlite:///{tmp_path / 'atomic-bounce.db'}")
    await backend.on_server_startup(host=LOCAL_HOST)
    await backend.admin_post_user(
        ADMIN,
        AdminUserPostRequest(user_id="alice", user_password="pw"),
    )
    draft = await backend.post_draft(
        ALICE,
        DraftPostRequest(subject="Atomic", body="body"),
    )
    original = await backend.send_draft(
        ALICE,
        draft.draft.draft_id,
        DraftSendPostRequest(recipients=["user:bob@remote.example"]),
    )
    delivery = (
        await backend.claim_due_federation_deliveries(
            now=original.sent_at,
            lease_owner="worker",
            lease_duration=timedelta(minutes=1),
            limit=1,
        )
    )[0]
    bounces = build_federation_bounces(
        delivery=delivery,
        failed_recipients=delivery.envelope.message.recipients,
        failure_code="host_rejected",
        timestamp=original.sent_at,
        emitter=BOUNCE_DAEMON,
        local_host=LOCAL_HOST,
    )

    async def fail_add(
        _repository: BounceEmissionRepository,
        _emission: object,
    ) -> None:
        raise RuntimeError("bounce reservation failed")

    monkeypatch.setattr(BounceEmissionRepository, "add", fail_add)
    try:
        with pytest.raises(RuntimeError, match="bounce reservation failed"):
            await backend.fail_federation_delivery(
                delivery.envelope_id,
                lease_owner="worker",
                completed_at=original.sent_at,
                failure_code="host_rejected",
                http_status=400,
                bounces=bounces,
            )
        restored = (
            await backend.get_outbound_federation_deliveries(original.message_id)
        )[0]
        assert restored.status == "leased"
        target = (await backend.get_message_delivery_targets(original.message_id))[0]
        assert target.status == "leased"
        assert await backend.get_bounce_emissions(original.message_id) == []
    finally:
        await backend.on_server_shutdown()
