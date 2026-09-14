# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Recipient grouping and immutable delivery-plan construction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from mail_protocol.core.federation import MAILInterServerMessage, mail_address_host
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.validators import validate_host

from mail_server.federation.records import (
    MessageDeliveryTarget,
    OutboundFederationDelivery,
)

UUIDFactory = Callable[[], object]


@dataclass(frozen=True, slots=True)
class MessageDeliveryPlan:
    """All target rows and remote envelopes created by one local send."""

    targets: tuple[MessageDeliveryTarget, ...]
    outbound: tuple[OutboundFederationDelivery, ...]

    @property
    def has_local_target(self) -> bool:
        return any(target.kind == "local" for target in self.targets)


def _new_id(factory: UUIDFactory) -> str:
    return str(factory())


def build_message_delivery_plan(
    message: MAILMessage,
    *,
    local_host: str,
    created_at: datetime,
    uuid_factory: UUIDFactory = uuid4,
) -> MessageDeliveryPlan:
    """Split recipients by host and build one durable target per destination."""

    validate_host(local_host)
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("delivery-plan creation time must be timezone-aware")

    local_host_normalized = local_host.lower()
    grouped: dict[str, list[str]] = {}
    display_hosts: dict[str, str] = {}
    for recipient in message.recipients:
        host = mail_address_host(recipient)
        normalized = host.lower()
        if recipient.startswith("list:") and normalized != local_host_normalized:
            raise ValueError("federated mailing-list recipients are not supported")
        grouped.setdefault(normalized, []).append(recipient)
        display_hosts.setdefault(normalized, host)

    targets: list[MessageDeliveryTarget] = []
    outbound: list[OutboundFederationDelivery] = []
    for normalized_host, recipients in grouped.items():
        destination_host = display_hosts[normalized_host]
        target_id = _new_id(uuid_factory)
        is_local = normalized_host == local_host_normalized
        target = MessageDeliveryTarget(
            target_id=target_id,
            message_id=message.message_id,
            origin="outbound",
            kind="local" if is_local else "remote",
            destination_host=destination_host,
            recipients=recipients,
            created_at=created_at,
            updated_at=created_at,
        )
        targets.append(target)
        if is_local:
            continue

        envelope_id = _new_id(uuid_factory)
        envelope = MAILInterServerMessage(
            message_id=envelope_id,
            sender_host=mail_address_host(message.sender),
            recipient_host=destination_host,
            message=message.model_copy(update={"recipients": list(recipients)}),
            metadata={},
            sent_at=created_at,
            protocol_version="1",
        )
        outbound.append(
            OutboundFederationDelivery(
                envelope_id=envelope_id,
                target_id=target_id,
                message_id=message.message_id,
                destination_host=destination_host,
                envelope=envelope,
                next_attempt_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )

    return MessageDeliveryPlan(targets=tuple(targets), outbound=tuple(outbound))
