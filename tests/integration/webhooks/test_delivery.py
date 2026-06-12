# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
Webhook delivery pipeline: payload shape, HMAC signing, and the retry
ladder in MAILServerBackend.handle_webhook_delivered_for_url.

Outbound POSTs are intercepted with respx; the retry ladder is observed
by patching asyncio.sleep, so the 6h schedule runs instantly.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime

import httpx
import pytest
import respx
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.user_agents import (
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgentInBackend,
)
from mail_protocol.core.webhooks import MAILWebhook
from mail_protocol.network.requests import DaemonDeliverLocalRequest
from mail_server.backends.memory.api import MemoryBackend

WEBHOOK_URL = "https://hooks.example.com/mail-events"
SECRET = "test-webhook-secret"
RECIPIENT = "sage@chorus@localhost"
SENDER = "user:alice@localhost"
MESSAGE_ID = "33333333-3333-4333-8333-333333333333"

# The full retry schedule: first attempt is immediate, then five waits.
RETRY_LADDER = [1, 30, 300, 3600, 6 * 3600]


@pytest.fixture
def message() -> MAILMessage:
    return MAILMessage(
        message_id=MESSAGE_ID,
        sender=SENDER,
        recipients=[RECIPIENT],
        subject="Webhook test",
        body="A body worth signing.",
        sent_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
        metadata={},
    )


@pytest.fixture
def pipeline_backend() -> MemoryBackend:
    # handle_webhook_delivered_for_url touches no backend state, so an
    # un-started instance is enough for the direct pipeline tests.
    return MemoryBackend()


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return slept


async def _fire(backend: MemoryBackend, message: MAILMessage, **kwargs) -> None:
    await backend.handle_webhook_delivered_for_url(
        url=WEBHOOK_URL,
        recipient=RECIPIENT,
        message=message,
        secret=SECRET,
        **kwargs,
    )


# ─── Payload shape and signing ─────────────────────────────────────


@respx.mock
async def test_delivery_posts_expected_payload(
    pipeline_backend: MemoryBackend, message: MAILMessage
) -> None:
    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
    await _fire(pipeline_backend, message)

    assert route.call_count == 1
    request = route.calls[0].request
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["X-MAIL-Event-Id"].startswith("evt_")
    int(request.headers["X-MAIL-Timestamp"])  # integral wall-clock time

    body = json.loads(request.content)
    assert body["event"] == "mail.delivered"
    assert body["event_id"] == request.headers["X-MAIL-Event-Id"]
    payload_message = body["message"]
    assert payload_message["message_id"] == f"msg_{MESSAGE_ID}"
    assert payload_message["sender"] == SENDER
    assert payload_message["recipient"] == RECIPIENT
    assert payload_message["subject"] == "Webhook test"
    assert payload_message["body"] == "A body worth signing."
    assert payload_message["swarm"] == "chorus"
    assert payload_message["metadata"] == {}


@respx.mock
async def test_receiver_can_verify_signature_from_wire_values(
    pipeline_backend: MemoryBackend, message: MAILMessage
) -> None:
    """
    The HMAC must be recomputable from values the receiver sees on the
    wire alone: sha256(secret, "{X-MAIL-Timestamp}.{raw body}").
    """

    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
    await _fire(pipeline_backend, message)

    request = route.calls[0].request
    timestamp = request.headers["X-MAIL-Timestamp"]
    expected = hmac.new(
        key=SECRET.encode(),
        msg=f"{timestamp}.{request.content.decode()}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()
    assert request.headers["X-MAIL-Signature"] == f"sha256={expected}"

    # A receiver holding the wrong secret computes a different MAC.
    wrong = hmac.new(
        key=b"some-other-secret",
        msg=f"{timestamp}.{request.content.decode()}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()
    assert request.headers["X-MAIL-Signature"] != f"sha256={wrong}"


@respx.mock
async def test_list_delivery_carries_originating_list_address(
    pipeline_backend: MemoryBackend, message: MAILMessage
) -> None:
    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
    await _fire(
        pipeline_backend,
        message,
        list_address="list:welfare-discourse@chorus@localhost",
    )

    body = json.loads(route.calls[0].request.content)
    assert body["message"]["metadata"] == {
        "list_address": "list:welfare-discourse@chorus@localhost"
    }


# ─── Retry ladder ──────────────────────────────────────────────────


@respx.mock
async def test_5xx_retries_until_success(
    pipeline_backend: MemoryBackend,
    message: MAILMessage,
    recorded_sleeps: list[float],
) -> None:
    route = respx.post(WEBHOOK_URL).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(503),
            httpx.Response(200),
        ]
    )
    await _fire(pipeline_backend, message)

    assert route.call_count == 3
    assert recorded_sleeps == RETRY_LADDER[:2]

    # The event id is stable across attempts (receiver-side dedup key).
    event_ids = {
        call.request.headers["X-MAIL-Event-Id"] for call in route.calls
    }
    assert len(event_ids) == 1


@respx.mock
async def test_4xx_is_permanent_failure_with_no_retry(
    pipeline_backend: MemoryBackend,
    message: MAILMessage,
    recorded_sleeps: list[float],
) -> None:
    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(410))
    await _fire(pipeline_backend, message)

    assert route.call_count == 1
    assert recorded_sleeps == []


@respx.mock
async def test_429_is_retried(
    pipeline_backend: MemoryBackend,
    message: MAILMessage,
    recorded_sleeps: list[float],
) -> None:
    route = respx.post(WEBHOOK_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200)]
    )
    await _fire(pipeline_backend, message)

    assert route.call_count == 2
    assert recorded_sleeps == RETRY_LADDER[:1]


@respx.mock
async def test_timeout_is_retried(
    pipeline_backend: MemoryBackend,
    message: MAILMessage,
    recorded_sleeps: list[float],
) -> None:
    route = respx.post(WEBHOOK_URL).mock(
        side_effect=[
            httpx.TimeoutException("connect timeout"),
            httpx.Response(200),
        ]
    )
    await _fire(pipeline_backend, message)

    assert route.call_count == 2
    assert recorded_sleeps == RETRY_LADDER[:1]


@respx.mock
async def test_gives_up_after_six_attempts(
    pipeline_backend: MemoryBackend,
    message: MAILMessage,
    recorded_sleeps: list[float],
    caplog: pytest.LogCaptureFixture,
) -> None:
    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(500))
    with caplog.at_level(logging.WARNING, logger="mail_server.backends.base"):
        await _fire(pipeline_backend, message)

    assert route.call_count == 6
    assert recorded_sleeps == RETRY_LADDER
    assert "failed" in caplog.text


# ─── Wiring: delivery fires registered webhooks ────────────────────


@respx.mock
async def test_daemon_deliver_local_fires_registered_webhook(
    deployment_dir,
) -> None:
    """
    The full backend wiring: daemon_deliver_local -> _deliver_to_address
    -> _handle_webhook_delivered -> async task -> signed POST.
    """

    backend = MemoryBackend()
    await backend.on_server_startup(host="localhost")

    backend.user_agents[RECIPIENT] = MAILUserAgentInBackend(
        user_agent=MAILAgent(
            ua_type="agent", name="sage", swarm="chorus", host="localhost"
        ),
        hashed_password="irrelevant",
    )
    backend.inboxes[RECIPIENT] = []
    message = MAILMessage(
        message_id=MESSAGE_ID,
        sender=SENDER,
        recipients=[RECIPIENT],
        subject="Wired",
        body="Through the whole pipeline.",
        sent_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
        metadata={},
    )
    backend.messages[MESSAGE_ID] = message
    backend.outbox_entries[MESSAGE_ID] = MAILOutboxEntrySummary(
        message_id=MESSAGE_ID,
        recipients=[RECIPIENT],
        subject="Wired",
        body_size=len(message.body),
        sent_at=message.sent_at,
        delivered_at=None,
        delivered_by=None,
    )
    backend.webhooks[WEBHOOK_URL] = MAILWebhook(
        webhook_id="wh_44444444-4444-4444-8444-444444444444",
        url=WEBHOOK_URL,
        events=["mail.delivered"],
        secret=SECRET,
    )

    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
    daemon = MAILDaemon(ua_type="daemon", worker_name="dummy", host="localhost")
    await backend.daemon_deliver_local(
        daemon=daemon,
        payload=DaemonDeliverLocalRequest(message_ids=[MESSAGE_ID]),
    )

    # The webhook fires on a fire-and-forget task; yield to the loop
    # until it has run.
    for _ in range(20):
        if route.called:
            break
        await asyncio.sleep(0)

    assert route.call_count == 1
    assert MESSAGE_ID in backend.inboxes[RECIPIENT]
    body = json.loads(route.calls[0].request.content)
    assert body["message"]["recipient"] == RECIPIENT


@respx.mock
async def test_delivery_to_non_agent_recipient_fires_no_webhook(
    deployment_dir,
) -> None:
    """
    `mail.delivered` webhooks are agent-scoped at v1: the payload's
    required swarm field only exists for swarm-scoped addresses, so
    host-scoped recipients (user:/admin:/daemon:) receive mail without
    firing webhooks.
    """

    backend = MemoryBackend()
    await backend.on_server_startup(host="localhost")

    user_address = "user:alice@localhost"
    backend.user_agents[user_address] = MAILUserAgentInBackend(
        user_agent=MAILUser(ua_type="user", user_id="alice", host="localhost"),
        hashed_password="irrelevant",
    )
    backend.inboxes[user_address] = []
    message = MAILMessage(
        message_id=MESSAGE_ID,
        sender="user:bob@localhost",
        recipients=[user_address],
        subject="No hook",
        body="Delivered silently.",
        sent_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
        metadata={},
    )
    backend.messages[MESSAGE_ID] = message
    backend.outbox_entries[MESSAGE_ID] = MAILOutboxEntrySummary(
        message_id=MESSAGE_ID,
        recipients=[user_address],
        subject="No hook",
        body_size=len(message.body),
        sent_at=message.sent_at,
        delivered_at=None,
        delivered_by=None,
    )
    backend.webhooks[WEBHOOK_URL] = MAILWebhook(
        webhook_id="wh_44444444-4444-4444-8444-444444444444",
        url=WEBHOOK_URL,
        events=["mail.delivered"],
        secret=SECRET,
    )

    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
    daemon = MAILDaemon(ua_type="daemon", worker_name="dummy", host="localhost")
    await backend.daemon_deliver_local(
        daemon=daemon,
        payload=DaemonDeliverLocalRequest(message_ids=[MESSAGE_ID]),
    )
    for _ in range(20):
        await asyncio.sleep(0)

    # Mail is delivered, but no webhook fires for a user recipient.
    assert MESSAGE_ID in backend.inboxes[user_address]
    assert route.call_count == 0
