# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Safe, deterministic local delivery-status notification construction."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from mail_protocol.core.dsn import MAILDSN
from mail_protocol.core.federation import mail_address_host
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.user_agents import MAILDaemon

from mail_server.federation.records import (
    BounceDelivery,
    BounceEmission,
    MessageDeliveryTarget,
    OutboundFederationDelivery,
)

FAILURE_REASONS = {
    "recipient_not_found": "The recipient could not be found.",
    "host_unreachable": "The destination host could not be reached.",
    "host_rejected": "The destination host rejected the message.",
    "delivery_expired": "Delivery attempts expired before acceptance.",
    "payload_too_large": "The destination rejected the message size.",
    "policy_denied": "The destination policy denied the message.",
    "internal_error": "An internal delivery error occurred.",
}


def _stable_uuid(kind: str, original_message_id: str, recipient: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"mail-bounce:{kind}:{original_message_id}:{recipient}",
        )
    )


def is_dsn(message: MAILMessage) -> bool:
    """Return whether a message carries DSN metadata, including future DSNs."""

    return isinstance(message.metadata.get("dsn"), dict)


def build_bounce_delivery(
    *,
    original: MAILMessage,
    failed_recipient: str,
    failure_code: str,
    failed_at: str,
    timestamp: datetime,
    emitter: MAILDaemon,
    local_host: str,
    attempt_timestamps: Sequence[datetime] | None = None,
) -> BounceDelivery | None:
    """Build one local-only DSN, or suppress bounce-on-bounce/remote senders."""

    if (
        is_dsn(original)
        or mail_address_host(original.sender).lower() != local_host.lower()
    ):
        return None
    if (
        emitter.host.lower() != local_host.lower()
        or "bounce:emit" not in emitter.scopes
    ):
        raise ValueError("bounce emitter must be a local daemon with bounce:emit")

    attempts = list(attempt_timestamps) if attempt_timestamps is not None else None
    dsn = MAILDSN(
        failure_code=failure_code,
        failure_reason=FAILURE_REASONS.get(
            failure_code,
            "Delivery failed for an unspecified reason.",
        ),
        original_message_id=original.message_id,
        failed_recipient=failed_recipient,
        failed_at=failed_at,
        attempt_count=len(attempts) if attempts is not None else None,
        attempt_timestamps=attempts,
        timestamp=timestamp,
    )
    message_id = _stable_uuid("message", original.message_id, failed_recipient)
    target_id = _stable_uuid("target", original.message_id, failed_recipient)
    emission_id = _stable_uuid("emission", original.message_id, failed_recipient)
    message = MAILMessage(
        mail_version="2.0",
        message_id=message_id,
        reply_to=original.message_id,
        sender=emitter.get_address(),
        recipients=[original.sender],
        subject="Delivery status notification",
        body=(f"Delivery to {failed_recipient} failed. {dsn.failure_reason}"),
        tags=["delivery-status"],
        sent_at=timestamp,
        metadata={"dsn": dsn.model_dump(mode="json")},
    )
    return BounceDelivery(
        emission=BounceEmission(
            emission_id=emission_id,
            original_sender=original.sender,
            original_message_id=original.message_id,
            failed_recipient=failed_recipient,
            emitted_at=timestamp,
            outcome="emitted",
            dsn_message_id=message_id,
        ),
        message=message,
        target=MessageDeliveryTarget(
            target_id=target_id,
            message_id=message_id,
            origin="outbound",
            kind="local",
            destination_host=local_host,
            recipients=[original.sender],
            created_at=timestamp,
            updated_at=timestamp,
        ),
    )


def build_federation_bounces(
    *,
    delivery: OutboundFederationDelivery,
    failed_recipients: Sequence[str],
    failure_code: str,
    timestamp: datetime,
    emitter: MAILDaemon,
    local_host: str,
) -> tuple[BounceDelivery, ...]:
    """Build one DSN per terminally failed remote recipient."""

    failed_at = (
        "destination"
        if failure_code
        in {
            "recipient_not_found",
            "host_rejected",
            "payload_too_large",
            "policy_denied",
        }
        else "in_transit"
    )
    attempts = [*delivery.attempt_timestamps, timestamp]
    prepared = (
        build_bounce_delivery(
            original=delivery.envelope.message,
            failed_recipient=recipient,
            failure_code=failure_code,
            failed_at=failed_at,
            timestamp=timestamp,
            emitter=emitter,
            local_host=local_host,
            attempt_timestamps=attempts,
        )
        for recipient in failed_recipients
    )
    return tuple(item for item in prepared if item is not None)
