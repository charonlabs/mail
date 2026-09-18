# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Signed Federation v1 ingress behavior across both storage backends."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mail_protocol.core.federation import MAILInterServerMessage
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
)
from mail_protocol.network.requests import (
    AdminUserPostRequest,
    DaemonDeliverLocalRequest,
)
from mail_server.backends.base import MAILServerBackend
from mail_server.backends.memory.api import MemoryBackend
from mail_server.backends.sqlite.api import SQLiteBackend
from mail_server.federation.config import FederationConfig
from mail_server.federation.discovery import ResolvedFederationKey
from mail_server.federation.ingress import FederationIngressService
from mail_server.federation.keys import FederationPrivateKey
from mail_server.federation.signatures import sign_federation_request

LOCAL_HOST = "server-b.example.com"
REMOTE_HOST = "server-a.example.com"
OTHER_REMOTE_HOST = "server-c.example.com"
DELIVERY_URL = f"https://{LOCAL_HOST}/daemon/deliver/remote/v1"
ADMIN = MAILAdmin(ua_type="admin", admin_id="root", host=LOCAL_HOST)
BOB = MAILUserAgent(user_agent=MAILUser(ua_type="user", user_id="bob", host=LOCAL_HOST))
DAEMON = MAILDaemon(ua_type="daemon", worker_name="worker", host=LOCAL_HOST)
NOW = datetime.now(UTC).replace(microsecond=0)


def _public_value(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


@pytest.fixture
def origin_key() -> FederationPrivateKey:
    private = Ed25519PrivateKey.generate()
    return FederationPrivateKey("origin-active", private, _public_value(private))


class StaticDiscovery:
    def __init__(self, key: FederationPrivateKey) -> None:
        self.resolved = ResolvedFederationKey(
            key=key.manifest_key(),
            manifest_from_cache=False,
        )

    async def resolve_public_key(self, host: str, key_id: str) -> ResolvedFederationKey:
        assert host == REMOTE_HOST
        assert key_id == self.resolved.key.key_id
        return self.resolved

    async def refresh_public_key(self, host: str, key_id: str) -> ResolvedFederationKey:
        return await self.resolve_public_key(host, key_id)


@pytest.fixture(params=("memory", "sqlite"))
async def ingress_backend(
    request: pytest.FixtureRequest,
    deployment_dir: Path,
    tmp_path: Path,
) -> AsyncIterator[MAILServerBackend]:
    if request.param == "memory":
        backend: MAILServerBackend = MemoryBackend()
    else:
        backend = SQLiteBackend(f"sqlite:///{tmp_path / 'ingress.db'}")
    await backend.on_server_startup(host=LOCAL_HOST)
    await backend.admin_post_user(
        ADMIN,
        AdminUserPostRequest(user_id="bob", user_password="pw"),
    )
    yield backend
    await backend.on_server_shutdown()


def _config(
    origin_key: FederationPrivateKey,
    *,
    policy: str = "open",
) -> FederationConfig:
    return FederationConfig(
        public_host=LOCAL_HOST,
        delivery_url=DELIVERY_URL,
        signing_key=origin_key,
        public_keys=(origin_key.manifest_key(),),
        policy=policy,  # type: ignore[arg-type]
        allowlist=frozenset(),
        discovery_ttl_seconds=600,
        max_request_bytes=1024 * 1024,
    )


def _envelope(**overrides: Any) -> MAILInterServerMessage:
    message = MAILMessage(
        mail_version="2.0",
        message_id="55555555-5555-4555-8555-555555555555",
        reply_to="44444444-4444-4444-8444-444444444444",
        sender=f"user:alice@{REMOTE_HOST}",
        recipients=[f"user:bob@{LOCAL_HOST}"],
        subject="Federated hello",
        body="preserve me exactly",
        tags=["inbound"],
        sent_at=NOW - timedelta(seconds=30),
        metadata={"payload": {"nested": True}},
    )
    values: dict[str, Any] = {
        "message_id": "77777777-7777-4777-8777-777777777777",
        "sender_host": REMOTE_HOST,
        "recipient_host": LOCAL_HOST,
        "message": message,
        "metadata": {"trace": "origin"},
        "sent_at": NOW,
        "protocol_version": "1",
    }
    values.update(overrides)
    return MAILInterServerMessage.model_validate(
        values,
        context={"defer_federation_host_checks": True},
    )


async def _accept(
    backend: MAILServerBackend,
    origin_key: FederationPrivateKey,
    envelope: MAILInterServerMessage,
    *,
    config: FederationConfig | None = None,
    body: bytes | None = None,
):
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=envelope,
        signing_key=origin_key,
        created=NOW,
    )
    service = FederationIngressService(
        config=config or _config(origin_key),
        discovery=StaticDiscovery(origin_key),
        clock=lambda: NOW,
    )
    return await service.accept(
        backend=backend,
        method="POST",
        target_url=DELIVERY_URL,
        headers=signed.headers,
        body=signed.body if body is None else body,
        transport_is_secure=True,
    )


async def test_signed_envelope_is_queued_once_then_delivered_verbatim(
    ingress_backend: MAILServerBackend,
    origin_key: FederationPrivateKey,
) -> None:
    envelope = _envelope()
    accepted = await _accept(ingress_backend, origin_key, envelope)
    duplicate = await _accept(ingress_backend, origin_key, envelope)

    assert accepted.status_code == 202
    assert duplicate.status_code == 409
    assert duplicate.body.code == "duplicate_envelope"  # type: ignore[union-attr]
    assert await ingress_backend.daemon_clear_message_buffer(DAEMON) == [
        envelope.message.message_id
    ]
    assert await ingress_backend.daemon_clear_message_buffer(DAEMON) == []

    delivered = await ingress_backend.daemon_deliver_local(
        DAEMON,
        DaemonDeliverLocalRequest(message_ids=[envelope.message.message_id]),
    )
    assert [item.message_id for item in delivered] == [envelope.message.message_id]
    inbox_entry = await ingress_backend.get_inbox_message(
        BOB,
        envelope.message.message_id,
    )
    assert inbox_entry.message == envelope.message


@pytest.mark.parametrize(
    ("envelope", "status", "code"),
    [
        (
            _envelope(recipient_host=OTHER_REMOTE_HOST),
            403,
            "recipient_host_mismatch",
        ),
        (
            _envelope(
                message=_envelope().message.model_copy(
                    update={"sender": f"user:alice@{OTHER_REMOTE_HOST}"}
                )
            ),
            403,
            "sender_host_mismatch",
        ),
        (
            _envelope(
                message=_envelope().message.model_copy(
                    update={"recipients": [f"user:bob@{OTHER_REMOTE_HOST}"]}
                )
            ),
            400,
            "recipient_not_local",
        ),
        (
            _envelope(sent_at=NOW - timedelta(minutes=5, microseconds=1)),
            400,
            "invalid_envelope",
        ),
        (
            _envelope(
                message=_envelope().message.model_copy(
                    update={"recipients": [f"user:ghost@{LOCAL_HOST}"]}
                )
            ),
            404,
            "recipient_not_found",
        ),
    ],
)
async def test_ordered_ingress_rejections(
    ingress_backend: MAILServerBackend,
    origin_key: FederationPrivateKey,
    envelope: MAILInterServerMessage,
    status: int,
    code: str,
) -> None:
    result = await _accept(ingress_backend, origin_key, envelope)
    assert result.status_code == status
    assert result.body.code == code  # type: ignore[union-attr]


async def test_policy_denial_precedes_recipient_disclosure(
    ingress_backend: MAILServerBackend,
    origin_key: FederationPrivateKey,
) -> None:
    envelope = _envelope(
        message=_envelope().message.model_copy(
            update={"recipients": [f"user:ghost@{LOCAL_HOST}"]}
        )
    )
    result = await _accept(
        ingress_backend,
        origin_key,
        envelope,
        config=replace(_config(origin_key), policy="closed"),
    )
    assert result.status_code == 403
    assert result.body.code == "policy_denied"  # type: ignore[union-attr]


async def test_exact_body_tampering_is_an_authentication_failure(
    ingress_backend: MAILServerBackend,
    origin_key: FederationPrivateKey,
) -> None:
    envelope = _envelope()
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=envelope,
        signing_key=origin_key,
        created=NOW,
    )
    result = await _accept(
        ingress_backend,
        origin_key,
        envelope,
        body=signed.body + b" ",
    )
    assert result.status_code == 401
    assert result.body.code == "invalid_signature"  # type: ignore[union-attr]
