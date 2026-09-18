# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Internal durable records for MAIL Federation delivery state."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from mail_protocol.core.federation import MAILInterServerMessage, mail_address_host
from mail_protocol.core.validators import (
    validate_host,
    validate_mail_address,
    validate_mail_addresses,
    validate_uuid,
)
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

DeliveryTargetKind = Literal["local", "remote"]
DeliveryTargetOrigin = Literal["outbound", "inbound"]
DeliveryTargetStatus = Literal["pending", "leased", "succeeded", "failed"]
OutboundDeliveryStatus = Literal["pending", "leased", "succeeded", "dead_letter"]
BounceEmissionOutcome = Literal["emitted", "suppressed", "failed"]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return value


AwareDatetime = Annotated[datetime, AfterValidator(_aware)]
UUIDString = Annotated[str, AfterValidator(validate_uuid)]
HostString = Annotated[str, AfterValidator(validate_host)]
Recipients = Annotated[
    list[str],
    AfterValidator(validate_mail_addresses),
    Field(min_length=1),
]


class MessageDeliveryTarget(BaseModel):
    """One independently tracked local or remote destination for a message."""

    model_config = ConfigDict(extra="forbid")

    target_id: UUIDString
    message_id: UUIDString
    origin: DeliveryTargetOrigin
    kind: DeliveryTargetKind
    destination_host: HostString
    recipients: Recipients
    status: DeliveryTargetStatus = "pending"
    lease_owner: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    lease_until: AwareDatetime | None = None
    failure_code: (
        Annotated[
            str,
            Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$"),
        ]
        | None
    ) = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    completed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        leased = self.status == "leased"
        if leased and (self.lease_owner is None or self.lease_until is None):
            raise ValueError("leased targets require both lease_owner and lease_until")
        if not leased and (
            self.lease_owner is not None or self.lease_until is not None
        ):
            raise ValueError("only leased targets may carry lease fields")
        if self.status == "failed" and self.failure_code is None:
            raise ValueError("failed targets require failure_code")
        if self.status != "failed" and self.failure_code is not None:
            raise ValueError("failure_code is valid only for failed targets")
        terminal = self.status in {"succeeded", "failed"}
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal targets require completed_at")
        if self.kind == "remote" and any(
            recipient.startswith("list:") for recipient in self.recipients
        ):
            raise ValueError("remote federation targets cannot contain lists")
        if self.origin == "inbound" and self.kind != "local":
            raise ValueError("inbound targets must be local")
        if any(
            mail_address_host(recipient).lower() != self.destination_host.lower()
            for recipient in self.recipients
        ):
            raise ValueError("every target recipient must match destination_host")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at cannot precede created_at")
        if self.lease_until is not None and self.lease_until <= self.updated_at:
            raise ValueError("lease_until must be after updated_at")
        return self


class OutboundFederationDelivery(BaseModel):
    """Crash-safe state for one remote envelope and its retry lifecycle."""

    model_config = ConfigDict(extra="forbid")

    envelope_id: UUIDString
    target_id: UUIDString
    message_id: UUIDString
    destination_host: HostString
    envelope: MAILInterServerMessage
    status: OutboundDeliveryStatus = "pending"
    attempt_count: Annotated[int, Field(ge=0)] = 0
    attempt_timestamps: list[AwareDatetime] = Field(default_factory=list)
    peer_was_reached: bool = False
    next_attempt_at: AwareDatetime
    lease_owner: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    lease_until: AwareDatetime | None = None
    last_http_status: Annotated[int, Field(ge=100, le=599)] | None = None
    last_error: Annotated[str, Field(min_length=1, max_length=1024)] | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    completed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.envelope_id != self.envelope.message_id:
            raise ValueError("envelope_id must match envelope.message_id")
        if self.message_id != self.envelope.message.message_id:
            raise ValueError("message_id must match the inner message")
        if self.destination_host != self.envelope.recipient_host:
            raise ValueError("destination_host must match envelope.recipient_host")
        if self.attempt_count != len(self.attempt_timestamps):
            raise ValueError("attempt_count must match attempt_timestamps")
        leased = self.status == "leased"
        if leased and (self.lease_owner is None or self.lease_until is None):
            raise ValueError("leased deliveries require both lease fields")
        if not leased and (
            self.lease_owner is not None or self.lease_until is not None
        ):
            raise ValueError("only leased deliveries may carry lease fields")
        terminal = self.status in {"succeeded", "dead_letter"}
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal deliveries require completed_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at cannot precede created_at")
        if self.lease_until is not None and self.lease_until <= self.updated_at:
            raise ValueError("lease_until must be after updated_at")
        if any(attempt < self.created_at for attempt in self.attempt_timestamps):
            raise ValueError("attempt timestamps cannot precede created_at")
        if any(
            current < previous
            for previous, current in zip(
                self.attempt_timestamps,
                self.attempt_timestamps[1:],
                strict=False,
            )
        ):
            raise ValueError("attempt_timestamps must be chronological")
        return self


class InboundFederationReceipt(BaseModel):
    """A retained envelope ID and content binding for replay prevention."""

    model_config = ConfigDict(extra="forbid")

    envelope_id: UUIDString
    sender_host: HostString
    inner_message_id: UUIDString
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    accepted_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_expiry(self) -> Self:
        if self.expires_at <= self.accepted_at:
            raise ValueError("receipt expiry must be after acceptance")
        return self


class BounceEmission(BaseModel):
    """An auditable, rate-countable bounce emission outcome."""

    model_config = ConfigDict(extra="forbid")

    emission_id: UUIDString
    original_sender: Annotated[str, AfterValidator(validate_mail_address)]
    original_message_id: UUIDString
    failed_recipient: Annotated[str, AfterValidator(validate_mail_address)]
    emitted_at: AwareDatetime
    outcome: BounceEmissionOutcome
