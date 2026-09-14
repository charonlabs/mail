# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs

"""MAIL Bounces v1 delivery status notification metadata."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from mail_protocol.core.validators import validate_mail_address, validate_uuid


class MAILDSNFailureCode(StrEnum):
    """Failure codes defined by MAIL Bounces v1."""

    RECIPIENT_NOT_FOUND = "recipient_not_found"
    HOST_UNREACHABLE = "host_unreachable"
    HOST_REJECTED = "host_rejected"
    DELIVERY_EXPIRED = "delivery_expired"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    POLICY_DENIED = "policy_denied"
    INTERNAL_ERROR = "internal_error"


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return value


class MAILDSN(BaseModel):
    """The structured object stored under ``MAILMessage.metadata['dsn']``."""

    model_config = ConfigDict(extra="forbid")

    # A string rather than a closed enum so clients can render future codes.
    failure_code: Annotated[
        str,
        Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$"),
    ]
    failure_reason: Annotated[str, Field(min_length=1)]
    original_message_id: Annotated[str, AfterValidator(validate_uuid)]
    failed_recipient: Annotated[str, AfterValidator(validate_mail_address)]
    failed_at: Literal["origin", "destination", "in_transit"]
    attempt_count: Annotated[int, Field(ge=1)] | None = None
    attempt_timestamps: list[datetime] | None = None
    timestamp: Annotated[datetime, AfterValidator(_aware_datetime)]

    @field_validator("attempt_timestamps")
    @classmethod
    def validate_attempt_timestamps(
        cls, value: list[datetime] | None
    ) -> list[datetime] | None:
        if value is None:
            return None
        for timestamp in value:
            _aware_datetime(timestamp)
        return value

    @model_validator(mode="after")
    def validate_attempt_metadata(self) -> Self:
        if self.failed_at == "in_transit" and self.attempt_count is None:
            raise ValueError("in_transit DSNs require attempt_count")
        if self.failed_at == "origin" and (
            self.attempt_count is not None or self.attempt_timestamps is not None
        ):
            raise ValueError("origin DSNs must omit attempt metadata")

        if self.attempt_timestamps is not None:
            if self.attempt_count is None:
                raise ValueError("attempt_timestamps requires attempt_count")
            if len(self.attempt_timestamps) != self.attempt_count:
                raise ValueError(
                    "attempt_timestamps must contain exactly attempt_count entries"
                )
            if any(
                later < earlier
                for earlier, later in zip(
                    self.attempt_timestamps, self.attempt_timestamps[1:]
                )
            ):
                raise ValueError("attempt_timestamps must be ordered oldest-first")
        return self
