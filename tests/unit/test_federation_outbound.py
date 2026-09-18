# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Outbound Federation v1 attempts, retry ladder, and worker behavior."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mail_protocol.core.federation import MAILFederationManifest
from mail_protocol.core.user_agents import MAILAdmin, MAILUser, MAILUserAgent
from mail_protocol.network.requests import (
    AdminUserPostRequest,
    DraftPostRequest,
    DraftSendPostRequest,
)
from mail_server.backends.base import MAILServerBackend
from mail_server.backends.memory.api import MemoryBackend
from mail_server.backends.sqlite.api import SQLiteBackend
from mail_server.federation.config import FederationConfig, FederationRuntime
from mail_server.federation.discovery import (
    FederationDeliveryTarget,
    FederationDiscoveryError,
)
from mail_server.federation.keys import FederationPrivateKey
from mail_server.federation.outbound import (
    RETRY_DELAYS,
    FederationDeadLetterEvent,
    FederationHTTPResponse,
    FederationTransportError,
    HTTPFederationTransport,
    OutboundFederationService,
    classify_http_status,
    parse_retry_after,
)
from mail_server.federation.worker import FederationWorker

LOCAL_HOST = "origin.example.com"
REMOTE_HOST = "destination.example.com"
DELIVERY_URL = f"https://{REMOTE_HOST}/daemon/deliver/remote/v1"
ADMIN = MAILAdmin(ua_type="admin", admin_id="root", host=LOCAL_HOST)
ALICE = MAILUserAgent(
    user_agent=MAILUser(ua_type="user", user_id="alice", host=LOCAL_HOST)
)


def _key() -> FederationPrivateKey:
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


def _config(signing_key: FederationPrivateKey) -> FederationConfig:
    return FederationConfig(
        public_host=LOCAL_HOST,
        delivery_url=f"https://{LOCAL_HOST}/daemon/deliver/remote/v1",
        signing_key=signing_key,
        public_keys=(signing_key.manifest_key(),),
        policy="open",
        allowlist=frozenset(),
        discovery_ttl_seconds=600,
        max_request_bytes=1024 * 1024,
    )


class StaticDiscovery:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0
        self.manifest = MAILFederationManifest(
            protocol_version="1",
            mail_protocol_version="2.0",
            delivery_url=DELIVERY_URL,
            public_keys=[
                {
                    "key_id": "unused",
                    "algorithm": "ed25519",
                    "public_key": base64.b64encode(bytes(32)).decode("ascii"),
                }
            ],
        )

    async def get_manifest(
        self, _host: str, *, force_refresh: bool = False
    ) -> MAILFederationManifest:
        del force_refresh
        self.calls += 1
        if self.fail:
            raise FederationDiscoveryError("unreachable")
        return self.manifest

    async def prepare_delivery_target(
        self, destination_host: str, delivery_url: str
    ) -> FederationDeliveryTarget:
        return FederationDeliveryTarget(
            public_url=delivery_url,
            connection_url=delivery_url,
            authority=destination_host,
            sni_hostname=destination_host,
        )

    async def aclose(self) -> None:
        return None


class RecordingTransport:
    def __init__(self, responses: list[FederationHTTPResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def post(
        self,
        *,
        destination_host: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> FederationHTTPResponse:
        self.requests.append(
            {
                "destination_host": destination_host,
                "url": url,
                "headers": dict(headers),
                "body": body,
            }
        )
        return self.responses.pop(0)


class FailingTransport:
    def __init__(self, error: FederationTransportError) -> None:
        self.error = error

    async def post(self, **_kwargs: Any) -> FederationHTTPResponse:
        raise self.error


class PinnedDiscovery(StaticDiscovery):
    async def prepare_delivery_target(
        self, destination_host: str, delivery_url: str
    ) -> FederationDeliveryTarget:
        return FederationDeliveryTarget(
            public_url=delivery_url,
            connection_url="https://93.184.216.34/daemon/deliver/remote/v1",
            authority=destination_host,
            sni_hostname=destination_host,
        )


@pytest.fixture(params=("memory", "sqlite"))
async def outbound_backend(
    request: pytest.FixtureRequest,
    deployment_dir: Path,
    tmp_path: Path,
) -> AsyncIterator[MAILServerBackend]:
    if request.param == "memory":
        backend: MAILServerBackend = MemoryBackend()
    else:
        backend = SQLiteBackend(f"sqlite:///{tmp_path / 'outbound.db'}")
    await backend.on_server_startup(host=LOCAL_HOST)
    await backend.admin_post_user(
        ADMIN,
        AdminUserPostRequest(user_id="alice", user_password="pw"),
    )
    yield backend
    await backend.on_server_shutdown()


async def _send_and_claim(
    backend: MAILServerBackend,
    *,
    lease_owner: str = "worker",
    recipients: list[str] | None = None,
):
    draft = await backend.post_draft(
        ALICE,
        DraftPostRequest(subject="Outbound", body="federated body"),
    )
    message = await backend.send_draft(
        ALICE,
        draft.draft.draft_id,
        DraftSendPostRequest(recipients=recipients or [f"user:bob@{REMOTE_HOST}"]),
    )
    claimed = await backend.claim_due_federation_deliveries(
        now=message.sent_at,
        lease_owner=lease_owner,
        lease_duration=timedelta(minutes=1),
        limit=1,
    )
    return message, claimed[0]


def _header(headers: Mapping[str, str], name: str) -> str:
    return next(value for key, value in headers.items() if key.lower() == name.lower())


def test_status_classification_and_retry_after_parsing() -> None:
    assert classify_http_status(202) == "success"
    assert classify_http_status(409) == "success"
    assert classify_http_status(429) == "retry"
    assert classify_http_status(500) == "retry"
    assert classify_http_status(501) == "permanent"
    assert classify_http_status(400) == "permanent"
    assert classify_http_status(302) == "permanent"

    now = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
    assert parse_retry_after("17", now=now) == timedelta(seconds=17)
    assert parse_retry_after(format_datetime(now + timedelta(minutes=2)), now=now) == (
        timedelta(minutes=2)
    )
    assert parse_retry_after("invalid", now=now) is None
    assert parse_retry_after("999", now=now, cap=timedelta(seconds=20)) == (
        timedelta(seconds=20)
    )


async def test_http_transport_pins_connection_and_preserves_authority() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"accepted_at": None})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = HTTPFederationTransport(
        discovery=PinnedDiscovery(),
        client=client,
    )
    try:
        response = await transport.post(
            destination_host=REMOTE_HOST,
            url=DELIVERY_URL,
            headers={"Host": REMOTE_HOST, "Content-Type": "application/json"},
            body=b"{}",
        )
    finally:
        await client.aclose()

    assert response.status_code == 202
    assert requests[0].url.host == "93.184.216.34"
    assert requests[0].headers["Host"] == REMOTE_HOST
    assert requests[0].extensions["sni_hostname"] == REMOTE_HOST


@pytest.mark.parametrize("success_status", [202, 409])
async def test_success_signs_exact_body_and_completes_outbox(
    outbound_backend: MAILServerBackend,
    success_status: int,
) -> None:
    message, claimed = await _send_and_claim(outbound_backend)
    transport = RecordingTransport(
        [FederationHTTPResponse(success_status, {"Content-Type": "application/json"})]
    )
    service = OutboundFederationService(
        backend=outbound_backend,
        config=_config(_key()),
        discovery=StaticDiscovery(),
        transport=transport,
        clock=lambda: message.sent_at,
    )

    completed = await service.process(claimed, lease_owner="worker")

    assert completed.status == "succeeded"
    assert completed.attempt_count == 1
    assert completed.last_http_status == success_status
    assert completed.peer_was_reached
    assert (
        await outbound_backend.get_outbox_message(ALICE, message.message_id)
    ).delivered_at
    request = transport.requests[0]
    assert request["url"] == DELIVERY_URL
    assert request["body"]
    assert _header(request["headers"], "Content-Digest")
    assert _header(request["headers"], "Content-Type") == "application/json"
    assert _header(request["headers"], "Date")
    assert _header(request["headers"], "Signature-Input")
    assert _header(request["headers"], "Signature")
    assert _header(request["headers"], "X-MAIL-Federation-Attempt") == "1"
    assert _header(request["headers"], "X-MAIL-Federation-Delivery-Id")


async def test_full_retry_ladder_dead_letters_once_as_delivery_expired(
    outbound_backend: MAILServerBackend,
) -> None:
    message, delivery = await _send_and_claim(outbound_backend)
    now = [message.sent_at]
    transport = RecordingTransport([FederationHTTPResponse(503, {}) for _ in range(6)])
    events: list[FederationDeadLetterEvent] = []

    async def dead_letter(event: FederationDeadLetterEvent) -> None:
        events.append(event)

    service = OutboundFederationService(
        backend=outbound_backend,
        config=_config(_key()),
        discovery=StaticDiscovery(),
        transport=transport,
        dead_letter_handler=dead_letter,
        clock=lambda: now[0],
    )
    expected_times: list[datetime] = []
    for attempt in range(1, 7):
        result = await service.process(delivery, lease_owner="worker")
        expected_times.append(now[0])
        if attempt == 6:
            delivery = result
            break
        assert result.next_attempt_at == now[0] + RETRY_DELAYS[attempt - 1]
        now[0] = result.next_attempt_at
        delivery = (
            await outbound_backend.claim_due_federation_deliveries(
                now=now[0],
                lease_owner="worker",
                lease_duration=timedelta(minutes=1),
                limit=1,
            )
        )[0]

    assert delivery.status == "dead_letter"
    assert delivery.attempt_count == 6
    assert delivery.attempt_timestamps == expected_times
    targets = await outbound_backend.get_message_delivery_targets(message.message_id)
    assert targets[0].failure_code == "delivery_expired"
    assert [
        _header(request["headers"], "X-MAIL-Federation-Attempt")
        for request in transport.requests
    ] == ["1", "2", "3", "4", "5", "6"]
    delivery_ids = {
        _header(request["headers"], "X-MAIL-Federation-Delivery-Id")
        for request in transport.requests
    }
    assert len(delivery_ids) == 6
    assert len(events) == 1
    assert events[0].failure_code == "delivery_expired"
    assert events[0].failed_recipients == (f"user:bob@{REMOTE_HOST}",)


async def test_discovery_exhaustion_maps_to_host_unreachable(
    outbound_backend: MAILServerBackend,
) -> None:
    message, delivery = await _send_and_claim(outbound_backend)
    now = [message.sent_at]
    events: list[FederationDeadLetterEvent] = []

    async def dead_letter(event: FederationDeadLetterEvent) -> None:
        events.append(event)

    service = OutboundFederationService(
        backend=outbound_backend,
        config=_config(_key()),
        discovery=StaticDiscovery(fail=True),
        transport=RecordingTransport([]),
        dead_letter_handler=dead_letter,
        clock=lambda: now[0],
    )
    for attempt in range(1, 7):
        result = await service.process(delivery, lease_owner="worker")
        if attempt == 6:
            break
        now[0] = result.next_attempt_at
        delivery = (
            await outbound_backend.claim_due_federation_deliveries(
                now=now[0],
                lease_owner="worker",
                lease_duration=timedelta(minutes=1),
                limit=1,
            )
        )[0]

    assert result.status == "dead_letter"
    assert events[0].failure_code == "host_unreachable"


async def test_retry_after_overrides_the_ladder(
    outbound_backend: MAILServerBackend,
) -> None:
    message, delivery = await _send_and_claim(outbound_backend)
    service = OutboundFederationService(
        backend=outbound_backend,
        config=_config(_key()),
        discovery=StaticDiscovery(),
        transport=RecordingTransport(
            [FederationHTTPResponse(429, {"retry-after": "17"})]
        ),
        clock=lambda: message.sent_at,
    )
    result = await service.process(delivery, lease_owner="worker")
    assert result.next_attempt_at == message.sent_at + timedelta(seconds=17)


@pytest.mark.parametrize("peer_reached", [False, True])
async def test_transport_failure_is_sanitized_and_retried(
    outbound_backend: MAILServerBackend,
    peer_reached: bool,
) -> None:
    message, delivery = await _send_and_claim(outbound_backend)
    service = OutboundFederationService(
        backend=outbound_backend,
        config=_config(_key()),
        discovery=StaticDiscovery(),
        transport=FailingTransport(
            FederationTransportError("request_timed_out", peer_reached)
        ),
        clock=lambda: message.sent_at,
    )

    result = await service.process(delivery, lease_owner="worker")

    assert result.status == "pending"
    assert result.last_error == "request_timed_out"
    assert result.peer_was_reached is peer_reached


@pytest.mark.parametrize(
    ("status", "body", "failure_code", "diagnostic"),
    [
        (
            413,
            b'{"code":"payload_too_large","detail":"large"}',
            "payload_too_large",
            "peer returned HTTP 413 (payload_too_large)",
        ),
        (
            403,
            b'{"code":"policy_denied","detail":"no"}',
            "policy_denied",
            "peer returned HTTP 403 (policy_denied)",
        ),
        (
            400,
            b'{"code":"invalid_envelope","detail":"bad"}',
            "host_rejected",
            "peer returned HTTP 400 (invalid_envelope)",
        ),
        (501, b"", "host_rejected", "peer returned HTTP 501"),
    ],
)
async def test_permanent_peer_rejections_dead_letter_immediately(
    outbound_backend: MAILServerBackend,
    status: int,
    body: bytes,
    failure_code: str,
    diagnostic: str,
) -> None:
    message, delivery = await _send_and_claim(outbound_backend)
    events: list[FederationDeadLetterEvent] = []

    async def dead_letter(event: FederationDeadLetterEvent) -> None:
        events.append(event)

    service = OutboundFederationService(
        backend=outbound_backend,
        config=_config(_key()),
        discovery=StaticDiscovery(),
        transport=RecordingTransport([FederationHTTPResponse(status, {}, body)]),
        dead_letter_handler=dead_letter,
        clock=lambda: message.sent_at,
    )
    result = await service.process(delivery, lease_owner="worker")
    assert result.status == "dead_letter"
    assert result.attempt_count == 1
    assert result.last_error == diagnostic
    assert events[0].failure_code == failure_code


async def test_recipient_rejection_atomically_queues_remaining_recipients(
    outbound_backend: MAILServerBackend,
) -> None:
    missing = f"user:missing@{REMOTE_HOST}"
    accepted = f"user:bob@{REMOTE_HOST}"
    message, delivery = await _send_and_claim(
        outbound_backend,
        recipients=[missing, accepted],
    )
    events: list[FederationDeadLetterEvent] = []

    async def dead_letter(event: FederationDeadLetterEvent) -> None:
        events.append(event)

    service = OutboundFederationService(
        backend=outbound_backend,
        config=_config(_key()),
        discovery=StaticDiscovery(),
        transport=RecordingTransport(
            [
                FederationHTTPResponse(
                    404,
                    {"Content-Type": "application/json"},
                    (
                        b'{"code":"recipient_not_found","detail":"unknown",'
                        b'"failed_recipients":["' + missing.encode() + b'"]}'
                    ),
                )
            ]
        ),
        dead_letter_handler=dead_letter,
        clock=lambda: message.sent_at,
    )

    failed = await service.process(delivery, lease_owner="worker")

    assert failed.status == "dead_letter"
    assert events[0].failed_recipients == (missing,)
    targets = await outbound_backend.get_message_delivery_targets(message.message_id)
    assert len(targets) == 2
    assert next(
        target for target in targets if target.status == "failed"
    ).recipients == [
        missing,
        accepted,
    ]
    assert next(
        target for target in targets if target.status == "pending"
    ).recipients == [accepted]
    deliveries = await outbound_backend.get_outbound_federation_deliveries(
        message.message_id
    )
    assert len(deliveries) == 2
    replacement = next(item for item in deliveries if item.status == "pending")
    assert replacement.envelope_id != delivery.envelope_id
    assert replacement.message_id == delivery.message_id
    assert replacement.envelope.message.message_id == delivery.message_id
    assert replacement.envelope.message.recipients == [accepted]
    assert await outbound_backend.count_active_federation_deliveries() == 1


async def test_worker_claims_and_processes_due_batch(
    outbound_backend: MAILServerBackend,
) -> None:
    draft = await outbound_backend.post_draft(
        ALICE,
        DraftPostRequest(subject="Worker", body="process me"),
    )
    message = await outbound_backend.send_draft(
        ALICE,
        draft.draft.draft_id,
        DraftSendPostRequest(recipients=[f"user:bob@{REMOTE_HOST}"]),
    )
    service = OutboundFederationService(
        backend=outbound_backend,
        config=_config(_key()),
        discovery=StaticDiscovery(),
        transport=RecordingTransport([FederationHTTPResponse(202, {})]),
        clock=lambda: message.sent_at,
    )
    worker = FederationWorker(
        backend=outbound_backend,
        outbound=service,
        clock=lambda: message.sent_at,
        worker_id="worker",
    )
    assert await worker.run_once() == 1
    outbound = await outbound_backend.get_outbound_federation_deliveries(
        message.message_id
    )
    assert outbound[0].status == "succeeded"
    assert await outbound_backend.count_active_federation_deliveries() == 0


async def test_worker_start_and_clean_stop(outbound_backend: MAILServerBackend) -> None:
    sleeping = asyncio.Event()
    never = asyncio.Event()

    async def sleeper(_delay: float) -> None:
        sleeping.set()
        await never.wait()

    service = OutboundFederationService(
        backend=outbound_backend,
        config=_config(_key()),
        discovery=StaticDiscovery(),
        transport=RecordingTransport([]),
    )
    worker = FederationWorker(
        backend=outbound_backend,
        outbound=service,
        sleeper=sleeper,
        worker_id="lifecycle",
    )
    worker.start()
    await asyncio.wait_for(sleeping.wait(), timeout=1)
    await asyncio.wait_for(worker.stop(), timeout=1)


async def test_runtime_owns_worker_and_transport_lifecycle(
    outbound_backend: MAILServerBackend,
) -> None:
    runtime = FederationRuntime(config=_config(_key()), discovery=StaticDiscovery())  # type: ignore[arg-type]
    await runtime.start(outbound_backend)
    await asyncio.sleep(0)
    assert runtime.worker is not None
    assert runtime.transport is not None
    await asyncio.wait_for(runtime.aclose(), timeout=1)
    assert runtime.worker is None
    assert runtime.transport is None
