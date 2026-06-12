# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
SPEC.md §8 (Delivery) conformance.

§8.1 pre-send errors are enforced at the request-contract layer (the
HTTP 422 notification side is covered by the integration suite); §8.2
post-send behavior is enforced against the reference backend.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.user_agents import MAILDaemon
from mail_protocol.network.requests import (
    DaemonDeliverLocalRequest,
    DraftPostRequest,
    DraftSendPostRequest,
)
from mail_server.backends.memory.api import MemoryBackend
from pydantic import ValidationError

# ─── §8.1 Pre-send errors ──────────────────────────────────────────


def test_malformed_subject_prevents_message_creation() -> None:
    """§8.1: a message with a malformed subject (§7.4) MUST NOT be
    created and the user-agent MUST be notified."""

    with pytest.raises(ValidationError):
        DraftPostRequest(subject="", body="A body.")


def test_malformed_body_prevents_message_creation() -> None:
    """§8.1: a message with a malformed body (§7.5) MUST NOT be
    created and the user-agent MUST be notified."""

    with pytest.raises(ValidationError):
        DraftPostRequest(subject="A subject", body="")


def test_malformed_recipient_prevents_send() -> None:
    """§8.1: a message containing one or more malformed addresses (§6)
    MUST NOT be delivered and the sender MUST be notified."""

    with pytest.raises(ValidationError):
        DraftSendPostRequest(recipients=["sage@chorus@localhost", "nope"])


# ─── §8.2 Post-send errors ─────────────────────────────────────────


async def test_undeliverable_message_is_preserved_and_logged(
    deployment_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """§8.2: if a valid message cannot be delivered to one or more
    intended recipients, the message MUST be preserved and the error
    SHOULD be logged."""

    backend = MemoryBackend()
    await backend.on_server_startup(host="localhost")

    message_id = "66666666-6666-4666-8666-666666666666"
    message = MAILMessage(
        message_id=message_id,
        sender="user:alice@localhost",
        recipients=["ghost@nowhere@localhost"],
        subject="Undeliverable",
        body="No such recipient.",
        sent_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
        metadata={},
    )
    backend.messages[message_id] = message
    backend.outbox_entries[message_id] = MAILOutboxEntrySummary(
        message_id=message_id,
        recipients=message.recipients,
        subject=message.subject,
        body_size=len(message.body),
        sent_at=message.sent_at,
        delivered_at=None,
        delivered_by=None,
    )

    daemon = MAILDaemon(ua_type="daemon", worker_name="dummy", host="localhost")
    with caplog.at_level(logging.WARNING, logger="mail_server.backends.memory.api"):
        await backend.daemon_deliver_local(
            daemon=daemon,
            payload=DaemonDeliverLocalRequest(message_ids=[message_id]),
        )

    # The message is preserved on the server...
    assert backend.messages[message_id] == message
    # ...and the failed recipient was logged.
    assert "ghost@nowhere@localhost" in caplog.text
