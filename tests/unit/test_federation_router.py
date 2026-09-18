# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""HTTP boundary tests for Federation v1 discovery and raw-body ingress."""

from __future__ import annotations

import asyncio
import base64
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mail_protocol.core.federation import MAILInterServerMessage
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.user_agents import MAILUser, MAILUserAgentInBackend
from mail_server.backends.memory.api import MemoryBackend
from mail_server.federation.config import (
    FederationConfig,
    FederationConfigurationError,
    FederationRuntime,
)
from mail_server.federation.discovery import ResolvedFederationKey
from mail_server.federation.keys import FederationPrivateKey
from mail_server.federation.signatures import sign_federation_request
from mail_server.routers.federation import router

LOCAL_HOST = "server-b.example.com"
REMOTE_HOST = "server-a.example.com"
DELIVERY_URL = f"https://{LOCAL_HOST}/daemon/deliver/remote/v1"
RECIPIENT = f"user:bob@{LOCAL_HOST}"


def _signing_key() -> FederationPrivateKey:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return FederationPrivateKey(
        "active",
        private,
        base64.b64encode(public).decode("ascii"),
    )


class _Discovery:
    def __init__(self, key: FederationPrivateKey) -> None:
        self.value = ResolvedFederationKey(
            key=key.manifest_key(), manifest_from_cache=False
        )

    async def resolve_public_key(
        self, _host: str, _key_id: str
    ) -> ResolvedFederationKey:
        return self.value

    async def refresh_public_key(
        self, _host: str, _key_id: str
    ) -> ResolvedFederationKey:
        return self.value


def _config(key: FederationPrivateKey) -> FederationConfig:
    return FederationConfig(
        public_host=LOCAL_HOST,
        delivery_url=DELIVERY_URL,
        signing_key=key,
        public_keys=(key.manifest_key(),),
        policy="open",
        allowlist=frozenset(),
        discovery_ttl_seconds=600,
        max_request_bytes=1024 * 1024,
    )


def _app(config: FederationConfig | None, discovery: object | None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.federation = SimpleNamespace(
        enabled=config is not None,
        config=config,
        discovery=discovery,
    )
    return app


def test_federation_configuration_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MAIL_FEDERATION_ENABLED", raising=False)
    assert FederationConfig.from_env() is None


def test_enabled_configuration_loads_key_and_fails_on_host_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = Ed25519PrivateKey.generate()
    key_path = tmp_path / "federation.pem"
    key_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    os.chmod(key_path, 0o600)
    values = {
        "MAIL_FEDERATION_ENABLED": "true",
        "MAIL_FEDERATION_PUBLIC_HOST": LOCAL_HOST,
        "MAIL_FEDERATION_DELIVERY_URL": DELIVERY_URL,
        "MAIL_FEDERATION_KEY_ID": "active",
        "MAIL_FEDERATION_PRIVATE_KEY_FILE": str(key_path),
        "MAIL_FEDERATION_POLICY": "open",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    config = FederationConfig.from_env()
    assert config is not None
    assert config.manifest.public_keys == [config.signing_key.manifest_key()]
    assert config.worker_batch_size == 20
    assert config.worker_lease_seconds == 30
    assert config.retry_after_cap_seconds == 86400
    monkeypatch.setenv("MAIL_FEDERATION_WORKER_LEASE_SECONDS", "10")
    with pytest.raises(FederationConfigurationError, match="lease must exceed"):
        FederationConfig.from_env()
    monkeypatch.delenv("MAIL_FEDERATION_WORKER_LEASE_SECONDS")
    with pytest.raises(FederationConfigurationError, match="must match"):
        FederationRuntime.from_env(local_host="wrong.example.com")


def test_disabled_federation_publishes_nothing() -> None:
    with TestClient(_app(None, None), base_url=f"https://{LOCAL_HOST}") as client:
        assert client.get("/.well-known/mail-federation").status_code == 404
        assert (
            client.post("/daemon/deliver/remote/v1", content=b"{}").status_code == 404
        )


def test_manifest_contains_only_public_values_and_cache_ttl() -> None:
    key = _signing_key()
    config = _config(key)
    with TestClient(
        _app(config, _Discovery(key)), base_url=f"https://{LOCAL_HOST}"
    ) as client:
        response = client.get("/.well-known/mail-federation")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.headers["Cache-Control"] == "public, max-age=600"
    assert response.json()["public_keys"] == [key.manifest_key().model_dump()]
    assert "private_key" not in response.text
    assert "allowlist" not in response.json()


def test_raw_body_cap_runs_before_authentication() -> None:
    key = _signing_key()
    config = replace(_config(key), max_request_bytes=32)
    with TestClient(
        _app(config, _Discovery(key)), base_url=f"https://{LOCAL_HOST}"
    ) as client:
        response = client.post(
            "/daemon/deliver/remote/v1",
            content=b"x" * 33,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_signed_route_commits_before_202_and_replays_as_409(
    deployment_dir: Path,
) -> None:
    del deployment_dir
    key = _signing_key()
    config = _config(key)
    now = datetime.now(UTC).replace(microsecond=0)
    envelope = MAILInterServerMessage(
        message_id="77777777-7777-4777-8777-777777777777",
        sender_host=REMOTE_HOST,
        recipient_host=LOCAL_HOST,
        message=MAILMessage(
            mail_version="2.0",
            message_id="55555555-5555-4555-8555-555555555555",
            sender=f"user:alice@{REMOTE_HOST}",
            recipients=[RECIPIENT],
            subject="HTTP ingress",
            body="exact bytes",
            tags=[],
            sent_at=now,
            metadata={"preserved": True},
        ),
        metadata={},
        sent_at=now,
        protocol_version="1",
    )
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=envelope,
        signing_key=key,
        created=now,
    )

    backend = MemoryBackend()
    asyncio.run(backend.on_server_startup(host=LOCAL_HOST))
    backend.user_agents[RECIPIENT] = MAILUserAgentInBackend(
        user_agent=MAILUser(ua_type="user", user_id="bob", host=LOCAL_HOST),
        hashed_password="unused",
    )
    app = _app(config, _Discovery(key))
    app.state.backend = backend
    try:
        with TestClient(app, base_url=f"https://{LOCAL_HOST}") as client:
            first = client.post(
                "/daemon/deliver/remote/v1",
                content=signed.body,
                headers=dict(signed.headers),
            )
            second = client.post(
                "/daemon/deliver/remote/v1",
                content=signed.body,
                headers=dict(signed.headers),
            )
    finally:
        asyncio.run(backend.on_server_shutdown())

    assert first.status_code == 202
    assert second.status_code == 409
    assert backend.message_buffer == [envelope.message.message_id]
    assert envelope.message.message_id in backend.messages
