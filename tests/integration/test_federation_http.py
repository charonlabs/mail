# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Signed HTTP ingress through local delivery and webhook on both backends."""

from __future__ import annotations

import base64
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from mail_protocol.core.federation import MAILInterServerMessage
from mail_protocol.core.messages import MAILMessage
from mail_server.backends.base import MAILServerBackend
from mail_server.federation.config import FederationConfig
from mail_server.federation.discovery import ResolvedFederationKey
from mail_server.federation.keys import FederationPrivateKey
from mail_server.federation.signatures import sign_federation_request

LOCAL_HOST = "localhost"
REMOTE_HOST = "origin.example.com"
RECIPIENT = f"sage@chorus@{LOCAL_HOST}"
DAEMON = f"daemon:dummy@{LOCAL_HOST}"
ADMIN = f"admin:ryan@{LOCAL_HOST}"


def _key() -> FederationPrivateKey:
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return FederationPrivateKey(
        "origin-active",
        private,
        base64.b64encode(raw).decode("ascii"),
    )


class StaticDiscovery:
    def __init__(self, key: FederationPrivateKey) -> None:
        self.resolved = ResolvedFederationKey(
            key=key.manifest_key(),
            manifest_from_cache=False,
        )

    async def resolve_public_key(
        self, host: str, key_id: str
    ) -> ResolvedFederationKey:
        assert host == REMOTE_HOST
        assert key_id == self.resolved.key.key_id
        return self.resolved

    async def refresh_public_key(
        self, host: str, key_id: str
    ) -> ResolvedFederationKey:
        return await self.resolve_public_key(host, key_id)


def test_signed_http_ingress_delivers_once_and_fires_webhook(
    app_client: TestClient,
    backend: MAILServerBackend,
    headers_for,
    monkeypatch,
) -> None:
    origin_key = _key()
    delivery_url = f"https://{LOCAL_HOST}/daemon/deliver/remote/v1"
    config = FederationConfig(
        public_host=LOCAL_HOST,
        delivery_url=delivery_url,
        signing_key=origin_key,
        public_keys=(origin_key.manifest_key(),),
        policy="open",
        allowlist=frozenset(),
        discovery_ttl_seconds=600,
        max_request_bytes=1024 * 1024,
        allow_private_hosts=True,
        allow_insecure_transport=True,
    )

    async def close_runtime() -> None:
        return None

    app_client.app.state.federation = SimpleNamespace(
        enabled=True,
        config=config,
        discovery=StaticDiscovery(origin_key),
        aclose=close_runtime,
    )
    webhook = app_client.post(
        "/admin/webhooks",
        json={
            "url": "https://hooks.example.com/federation",
            "events": ["mail.delivered"],
            "secret": "integration-secret",
        },
        headers=headers_for(ADMIN),
    )
    assert webhook.status_code == 200, webhook.text
    webhook_calls: list[dict] = []

    async def capture_webhook(**kwargs) -> None:
        webhook_calls.append(kwargs)

    monkeypatch.setattr(backend, "handle_webhook_delivered_for_url", capture_webhook)
    now = datetime.now(UTC).replace(microsecond=0)
    message = MAILMessage(
        mail_version="2.0",
        message_id=str(uuid4()),
        sender=f"user:alice@{REMOTE_HOST}",
        recipients=[RECIPIENT],
        subject="Signed HTTP integration",
        body="preserve this exact body",
        tags=["federated"],
        sent_at=now,
        metadata={"nested": {"preserved": True}},
    )
    envelope = MAILInterServerMessage(
        message_id=str(uuid4()),
        sender_host=REMOTE_HOST,
        recipient_host=LOCAL_HOST,
        message=message,
        metadata={"trace": "integration"},
        sent_at=now,
        protocol_version="1",
    )
    signed = sign_federation_request(
        url=delivery_url,
        envelope=envelope,
        signing_key=origin_key,
        created=now,
    )

    first = app_client.post(
        "/daemon/deliver/remote/v1",
        content=signed.body,
        headers=dict(signed.headers),
    )
    duplicate = app_client.post(
        "/daemon/deliver/remote/v1",
        content=signed.body,
        headers=dict(signed.headers),
    )
    assert first.status_code == 202, first.text
    assert duplicate.status_code == 409, duplicate.text

    daemon_headers = headers_for(DAEMON)
    claimed = app_client.post(
        "/daemon/message-buffer/clear",
        headers=daemon_headers,
    )
    assert claimed.json()["message_ids"] == [message.message_id]
    delivered = app_client.post(
        "/daemon/deliver/local",
        json={"message_ids": [message.message_id]},
        headers=daemon_headers,
    )
    assert delivered.status_code == 200, delivered.text
    deadline = time.monotonic() + 2
    while not webhook_calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(webhook_calls) == 1
    assert webhook_calls[0]["recipient"] == RECIPIENT

    opened = app_client.get(
        f"/inbox/{message.message_id}",
        headers=headers_for(RECIPIENT),
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["entry"]["message"] == message.model_dump(mode="json")
