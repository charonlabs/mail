# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs

"""Shared MAIL Federation v1 discovery and envelope models."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.validators import (
    validate_host,
    validate_mail_address,
    validate_uuid,
)

FEDERATION_PROTOCOL_VERSION = "1"
ED25519_PUBLIC_KEY_BYTES = 32


def mail_address_host(address: str) -> str:
    """Validate a MAIL address and return its final host segment."""

    validate_mail_address(address)
    return address.rsplit("@", 1)[1]


def _aware_datetime(value: datetime) -> datetime:
    """Require a datetime carrying a usable UTC offset."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return value


class MAILFederationPublicKey(BaseModel):
    """One public signing key advertised by a federation peer."""

    model_config = ConfigDict(extra="forbid")

    key_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
        ),
    ]
    algorithm: Literal["ed25519"]
    public_key: str

    @field_validator("public_key")
    @classmethod
    def validate_public_key(cls, value: str) -> str:
        """Validate canonical base64 containing a raw Ed25519 public key."""

        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("public_key must be valid base64") from exc
        if len(decoded) != ED25519_PUBLIC_KEY_BYTES:
            raise ValueError("public_key must decode to a 32-byte Ed25519 public key")
        return value


class MAILFederationPolicyHints(BaseModel):
    """Informational acceptance hint in a discovery manifest."""

    model_config = ConfigDict(extra="forbid")

    accepts: Literal["open", "allowlist", "closed"]


class MAILFederationManifest(BaseModel):
    """The document served from ``/.well-known/mail-federation``."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["1"]
    mail_protocol_version: Literal["2.0"] | None = None
    delivery_url: AnyHttpUrl
    public_keys: Annotated[list[MAILFederationPublicKey], Field(min_length=1)]
    policy_hints: MAILFederationPolicyHints | None = None

    @field_validator("delivery_url")
    @classmethod
    def validate_delivery_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("delivery_url must use HTTPS")
        return value

    @model_validator(mode="after")
    def validate_unique_key_ids(self) -> Self:
        key_ids = [key.key_id for key in self.public_keys]
        if len(key_ids) != len(set(key_ids)):
            raise ValueError("public_keys must contain unique key_id values")
        return self


class MAILInterServerMessage(BaseModel):
    """A signed Federation v1 envelope around one destination's message copy."""

    model_config = ConfigDict(extra="forbid")

    message_id: Annotated[str, AfterValidator(validate_uuid)]
    sender_host: Annotated[str, AfterValidator(validate_host)]
    recipient_host: Annotated[str, AfterValidator(validate_host)]
    message: MAILMessage
    metadata: dict[str, Any]
    sent_at: Annotated[datetime, AfterValidator(_aware_datetime)]
    protocol_version: Literal["1"]

    @model_validator(mode="after")
    def validate_envelope_identity_and_destination(self) -> Self:
        if self.message_id == self.message.message_id:
            raise ValueError("envelope message_id must differ from inner message_id")

        if mail_address_host(self.message.sender) != self.sender_host:
            raise ValueError("sender_host must match the inner message sender host")

        for recipient in self.message.recipients:
            if recipient.startswith("list:"):
                raise ValueError("federated mailing-list recipients are not supported")
            if mail_address_host(recipient) != self.recipient_host:
                raise ValueError(
                    "every inner message recipient must match recipient_host"
                )
        return self
