# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs

"""MAIL Federation v1 HTTP path, header, and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from mail_protocol.core.validators import validate_mail_addresses

FEDERATION_DISCOVERY_PATH = "/.well-known/mail-federation"
FEDERATION_DELIVERY_PATH_V1 = "/daemon/deliver/remote/v1"

FEDERATION_ATTEMPT_HEADER = "X-MAIL-Federation-Attempt"
FEDERATION_DELIVERY_ID_HEADER = "X-MAIL-Federation-Delivery-Id"


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return value


class MAILFederationAcceptedResponse(BaseModel):
    """Optional response body accompanying a Federation v1 ``202``."""

    model_config = ConfigDict(extra="forbid")

    accepted_at: Annotated[datetime, AfterValidator(_aware_datetime)] | None = None


class MAILFederationErrorResponse(BaseModel):
    """Machine-readable error body returned by Federation v1 endpoints."""

    model_config = ConfigDict(extra="forbid")

    # Open string for forward compatibility; v1's known codes live in SPEC.md.
    code: Annotated[
        str,
        Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$"),
    ]
    detail: Annotated[str, Field(min_length=1)]
    failed_recipients: (
        Annotated[
            list[str], AfterValidator(validate_mail_addresses), Field(min_length=1)
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_recipient_not_found_details(self) -> Self:
        if self.code == "recipient_not_found" and self.failed_recipients is None:
            raise ValueError("recipient_not_found errors require failed_recipients")
        if self.failed_recipients is not None and len(self.failed_recipients) != len(
            set(self.failed_recipients)
        ):
            raise ValueError("failed_recipients must not contain duplicates")
        return self
