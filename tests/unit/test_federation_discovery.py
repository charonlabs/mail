# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Unit tests for secure Federation v1 manifest discovery."""

import base64
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mail_protocol.core.federation import MAILInterServerMessage
from mail_protocol.core.messages import MAILMessage
from mail_server.federation.discovery import (
    FederationDiscoveryClient,
    FederationHostRejected,
    FederationManifestError,
)
from mail_server.federation.keys import FederationPrivateKey
from mail_server.federation.signatures import (
    sign_federation_request,
    verify_federation_request_with_discovery,
)

PUBLIC_ADDRESS = "93.184.216.34"


def public_value(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def manifest(public_key: str, *, key_id: str = "active") -> dict[str, Any]:
    return {
        "protocol_version": "1",
        "mail_protocol_version": "2.0",
        "delivery_url": "https://server-a.example.com/daemon/deliver/remote/v1",
        "public_keys": [
            {
                "key_id": key_id,
                "algorithm": "ed25519",
                "public_key": public_key,
            }
        ],
    }


async def public_resolver(_host: str, _port: int) -> Sequence[str]:
    return [PUBLIC_ADDRESS]


def client_for(
    handler: Any,
    **kwargs: Any,
) -> FederationDiscoveryClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return FederationDiscoveryClient(
        client=http_client,
        resolver=public_resolver,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_discovery_pins_dns_and_caches_manifest() -> None:
    key = Ed25519PrivateKey.generate()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json=manifest(public_value(key)),
        )

    discovery = client_for(handler)
    first = await discovery.get_manifest("server-a.example.com")
    second = await discovery.get_manifest("server-a.example.com")

    assert first is second
    assert len(requests) == 1
    assert requests[0].url.host == PUBLIC_ADDRESS
    assert requests[0].headers["Host"] == "server-a.example.com"
    assert requests[0].extensions["sni_hostname"] == "server-a.example.com"
    await discovery._client.aclose()


@pytest.mark.asyncio
async def test_discovery_cache_expires_at_configured_ttl() -> None:
    key = Ed25519PrivateKey.generate()
    now = [100.0]
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=manifest(public_value(key)),
        )

    discovery = client_for(handler, ttl_seconds=300, clock=lambda: now[0])
    await discovery.get_manifest("server-a.example.com")
    now[0] += 299
    await discovery.get_manifest("server-a.example.com")
    now[0] += 1
    await discovery.get_manifest("server-a.example.com")

    assert calls == 2
    await discovery._client.aclose()


@pytest.mark.asyncio
async def test_delivery_target_is_owned_and_dns_pinned() -> None:
    discovery = client_for(lambda _request: httpx.Response(500))
    target = await discovery.prepare_delivery_target(
        "server-a.example.com",
        "https://server-a.example.com/custom/delivery?version=1",
    )
    assert target.public_url == (
        "https://server-a.example.com/custom/delivery?version=1"
    )
    assert target.connection_url == (
        f"https://{PUBLIC_ADDRESS}/custom/delivery?version=1"
    )
    assert target.authority == "server-a.example.com"

    with pytest.raises(FederationManifestError, match="not owned"):
        await discovery.prepare_delivery_target(
            "server-a.example.com",
            "https://attacker.example.net/deliver",
        )
    await discovery._client.aclose()


@pytest.mark.asyncio
async def test_unknown_cached_key_forces_one_refresh() -> None:
    key = Ed25519PrivateKey.generate()
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        key_id = "old" if calls == 1 else "new"
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=manifest(public_value(key), key_id=key_id),
        )

    discovery = client_for(handler)
    await discovery.get_manifest("server-a.example.com")
    resolved = await discovery.resolve_public_key("server-a.example.com", "new")

    assert resolved.key.key_id == "new"
    assert resolved.manifest_from_cache is False
    assert calls == 2
    await discovery._client.aclose()


@pytest.mark.asyncio
async def test_cached_signature_failure_refreshes_rotated_key() -> None:
    old_key = Ed25519PrivateKey.generate()
    new_key = Ed25519PrivateKey.generate()
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        advertised = old_key if calls == 1 else new_key
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=manifest(public_value(advertised)),
        )

    discovery = client_for(handler)
    await discovery.get_manifest("server-a.example.com")
    now = datetime.now(UTC).replace(microsecond=0)
    envelope = MAILInterServerMessage(
        message_id="77777777-7777-4777-8777-777777777777",
        sender_host="server-a.example.com",
        recipient_host="server-b.example.com",
        message=MAILMessage(
            mail_version="2.0",
            message_id="55555555-5555-4555-8555-555555555555",
            sender="user:alice@server-a.example.com",
            recipients=["bob@village@server-b.example.com"],
            subject="Rotated key",
            body="hello",
            tags=[],
            sent_at=now,
            metadata={},
        ),
        metadata={},
        sent_at=now,
        protocol_version="1",
    )
    signed = sign_federation_request(
        url="https://server-b.example.com/daemon/deliver/remote/v1",
        envelope=envelope,
        signing_key=FederationPrivateKey("active", new_key, public_value(new_key)),
    )

    verified = await verify_federation_request_with_discovery(
        sender_host="server-a.example.com",
        method=signed.method,
        url=signed.url,
        headers=signed.headers,
        body=signed.body,
        discovery=discovery,
    )

    assert verified.key_id == "active"
    assert calls == 2
    await discovery._client.aclose()


@pytest.mark.asyncio
async def test_discovery_rejects_non_public_dns_answers() -> None:
    async def private_resolver(_host: str, _port: int) -> Sequence[str]:
        return ["127.0.0.1"]

    discovery = FederationDiscoveryClient(resolver=private_resolver)
    with pytest.raises(FederationHostRejected, match="non-public"):
        await discovery.get_manifest("server-a.example.com")
    await discovery.aclose()


@pytest.mark.asyncio
async def test_explicit_local_override_allows_isolated_interop() -> None:
    key = Ed25519PrivateKey.generate()

    async def local_resolver(_host: str, _port: int) -> Sequence[str]:
        return ["127.0.0.1"]

    def handler(_request: httpx.Request) -> httpx.Response:
        body = manifest(public_value(key))
        body["delivery_url"] = "https://localhost/remote/v1"
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=body,
        )

    discovery = FederationDiscoveryClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        resolver=local_resolver,
        allow_private_hosts=True,
    )
    result = await discovery.get_manifest("localhost")

    assert result.protocol_version == "1"
    await discovery._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "content_type", "body"),
    [
        (302, "application/json", b"{}"),
        (200, "text/plain", b"{}"),
        (200, "application/json", b"not json"),
    ],
)
async def test_discovery_rejects_invalid_http_contract(
    status: int,
    content_type: str,
    body: bytes,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={
                "Content-Type": content_type,
                "Location": "https://elsewhere.test",
            },
            content=body,
        )

    discovery = client_for(handler)
    with pytest.raises(FederationManifestError):
        await discovery.get_manifest("server-a.example.com")
    await discovery._client.aclose()


@pytest.mark.asyncio
async def test_discovery_caps_streamed_response_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=json.dumps({"padding": "x" * 1024}),
        )

    discovery = client_for(handler, max_response_bytes=128)
    with pytest.raises(FederationManifestError, match="response limit"):
        await discovery.get_manifest("server-a.example.com")
    await discovery._client.aclose()
