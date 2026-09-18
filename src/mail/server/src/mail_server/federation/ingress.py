# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Ordered validation and atomic acceptance for signed Federation v1 ingress."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
from mail_protocol.core.federation import MAILInterServerMessage, mail_address_host
from mail_protocol.core.validators import validate_host
from mail_protocol.network.federation import (
    MAILFederationAcceptedResponse,
    MAILFederationErrorResponse,
)
from pydantic import ValidationError

from mail_server.backends.base import MAILServerBackend
from mail_server.federation.config import FederationConfig
from mail_server.federation.discovery import FederationDiscoveryError
from mail_server.federation.keys import FederationKeyError
from mail_server.federation.policy import accepts_federation_peer
from mail_server.federation.records import InboundFederationReceipt
from mail_server.federation.signatures import (
    FederationSignatureError,
    HeaderInput,
    signature_key_id,
    verify_federation_request_with_discovery,
)

ENVELOPE_FRESHNESS = timedelta(minutes=5)
RECEIPT_RETENTION = timedelta(hours=24)


class DiscoveryResolver(Protocol):
    async def resolve_public_key(self, host: str, key_id: str) -> Any: ...

    async def refresh_public_key(self, host: str, key_id: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class FederationIngressResult:
    status_code: int
    body: MAILFederationAcceptedResponse | MAILFederationErrorResponse


def _error(
    status_code: int,
    code: str,
    detail: str,
    *,
    failed_recipients: list[str] | None = None,
) -> FederationIngressResult:
    return FederationIngressResult(
        status_code=status_code,
        body=MAILFederationErrorResponse(
            code=code,
            detail=detail,
            failed_recipients=failed_recipients,
        ),
    )


def _claimed_payload(body: bytes) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("request body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    sender_host = payload.get("sender_host")
    if not isinstance(sender_host, str):
        raise ValueError("sender_host must be a string")
    try:
        validate_host(sender_host)
    except ValueError as exc:
        raise ValueError("sender_host is invalid") from exc
    return payload, sender_host


def _inner_content_hash(envelope: MAILInterServerMessage) -> str:
    content = json.dumps(
        envelope.message.model_dump(mode="json", round_trip=True),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


class FederationIngressService:
    """Validate one exact request and commit it only after every check passes."""

    def __init__(
        self,
        *,
        config: FederationConfig,
        discovery: DiscoveryResolver,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.config = config
        self.discovery = discovery
        self.clock = clock

    async def accept(
        self,
        *,
        backend: MAILServerBackend,
        method: str,
        target_url: str,
        headers: HeaderInput,
        body: bytes,
        transport_is_secure: bool,
    ) -> FederationIngressResult:
        if not transport_is_secure and not self.config.allow_insecure_transport:
            return _error(
                400,
                "invalid_envelope",
                "federation delivery requires HTTPS",
            )

        try:
            parsed_headers = httpx.Headers(headers)
            host_values = parsed_headers.get_list("Host")
        except (TypeError, ValueError):
            host_values = []
        expected_authority = httpx.URL(self.config.delivery_url).netloc.decode("ascii")
        if (
            len(host_values) != 1
            or host_values[0].strip().lower() != expected_authority.lower()
        ):
            return _error(
                400,
                "invalid_envelope",
                "request authority does not match the federation endpoint",
            )

        # Validate the mandatory singleton signature headers before using any
        # body claim for network discovery.
        try:
            signature_key_id(headers)
        except FederationSignatureError:
            return _error(401, "invalid_signature", "invalid request signature")

        try:
            payload, claimed_sender_host = _claimed_payload(body)
        except ValueError:
            return _error(400, "invalid_envelope", "invalid federation envelope")

        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("federation ingress clock must be timezone-aware")
        now = now.astimezone(UTC)

        try:
            await verify_federation_request_with_discovery(
                sender_host=claimed_sender_host,
                method=method,
                url=target_url,
                headers=headers,
                body=body,
                discovery=self.discovery,
                now=now,
            )
        except (
            FederationDiscoveryError,
            FederationKeyError,
            FederationSignatureError,
        ):
            return _error(401, "invalid_signature", "invalid request signature")

        # The protocol model normally enforces cross-field host invariants.
        # In ingress those checks are deliberately deferred so each normative
        # validation step receives its specified status and error code.
        try:
            envelope = MAILInterServerMessage.model_validate(
                payload,
                context={"defer_federation_host_checks": True},
            )
        except ValidationError:
            return _error(400, "invalid_envelope", "invalid federation envelope")

        if envelope.recipient_host.lower() != self.config.public_host.lower():
            return _error(
                403,
                "recipient_host_mismatch",
                "recipient host does not match this server",
            )
        if (
            envelope.sender_host.lower() != claimed_sender_host.lower()
            or mail_address_host(envelope.message.sender).lower()
            != envelope.sender_host.lower()
        ):
            return _error(
                403,
                "sender_host_mismatch",
                "sender host does not match the verified origin",
            )
        if any(
            recipient.startswith("list:")
            or mail_address_host(recipient).lower() != envelope.recipient_host.lower()
            for recipient in envelope.message.recipients
        ):
            return _error(
                400,
                "recipient_not_local",
                "every recipient must be local to the destination",
            )
        if abs(now - envelope.sent_at.astimezone(UTC)) > ENVELOPE_FRESHNESS:
            return _error(
                400,
                "invalid_envelope",
                "federation envelope is outside the freshness window",
            )

        await backend.purge_expired_federation_receipts(now=now)
        if await backend.has_inbound_federation_receipt(envelope.message_id):
            return _error(409, "duplicate_envelope", "envelope already accepted")

        if not accepts_federation_peer(self.config, envelope.sender_host):
            return _error(
                403,
                "policy_denied",
                "federation peer is not accepted",
            )

        failed_recipients = [
            recipient
            for recipient in dict.fromkeys(envelope.message.recipients)
            if not await backend.user_agent_exists(recipient)
        ]
        if failed_recipients:
            return _error(
                404,
                "recipient_not_found",
                "one or more recipients were not found",
                failed_recipients=failed_recipients,
            )

        receipt = InboundFederationReceipt(
            envelope_id=envelope.message_id,
            sender_host=envelope.sender_host,
            inner_message_id=envelope.message.message_id,
            content_hash=_inner_content_hash(envelope),
            accepted_at=now,
            expires_at=now + RECEIPT_RETENTION,
        )
        try:
            accepted = await backend.accept_inbound_federation(
                receipt,
                envelope.message,
            )
        except ValueError:
            return _error(
                400,
                "invalid_envelope",
                "inner message ID collides with different content",
            )
        if not accepted:
            return _error(409, "duplicate_envelope", "envelope already accepted")
        return FederationIngressResult(
            status_code=202,
            body=MAILFederationAcceptedResponse(accepted_at=now),
        )
