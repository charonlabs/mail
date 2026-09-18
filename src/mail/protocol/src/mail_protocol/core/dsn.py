# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

FailureCode = Literal[
    "recipient_not_found",
    "host_unreachable",
    "host_rejected",
    "delivery_expired",
    "payload_too_large",
    "policy_denied",
    "internal_error",
]

FailedAt = Literal["origin", "destination", "in_transit"]


class MAILDSN(BaseModel):
    """
    Delivery Status Notification metadata per RFC-0002.

    Lives in the ``metadata.dsn`` field of a MAILMessage. Presence of this
    object is the authoritative signal that a message is a bounce (Delivery
    Status Notification), not a regular message. Clients rendering bounces MUST
    check for this field.
    """

    model_config = ConfigDict(extra="forbid")

    failure_code: FailureCode
    failure_reason: str
    original_message_id: str
    failed_recipient: str
    failed_at: FailedAt
    timestamp: datetime
    attempt_count: int | None = None
    attempt_timestamps: list[datetime] | None = None

    @model_validator(mode="after")
    def validate_attempt_fields(self) -> Self:
        """
        Validate retry-attempt fields whose constraints span multiple fields.
        """

        if self.attempt_count is None and self.attempt_timestamps is not None:
            raise ValueError(
                "attempt_timestamps must be absent when attempt_count is absent"
            )
        if (
            self.attempt_count is not None
            and self.attempt_timestamps is not None
            and len(self.attempt_timestamps) != self.attempt_count
        ):
            raise ValueError("attempt_timestamps length must equal attempt_count")
        if self.failed_at == "origin" and self.attempt_count is not None:
            raise ValueError("attempt_count must be absent for origin failures")

        return self
