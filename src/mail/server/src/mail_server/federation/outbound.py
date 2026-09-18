# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Signed outbound attempts, retry scheduling, and terminal result mapping."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
from mail_protocol.core.federation import MAILFederationManifest
from mail_protocol.network.federation import (
    FEDERATION_ATTEMPT_HEADER,
    FEDERATION_DELIVERY_ID_HEADER,
)

from mail_server.federation.config import FederationConfig
from mail_server.federation.discovery import (
    FederationDeliveryTarget,
    FederationDiscoveryError,
)
from mail_server.federation.records import (
    MessageDeliveryTarget,
    OutboundFederationDelivery,
)
from mail_server.federation.signatures import sign_federation_request

if TYPE_CHECKING:
    from mail_server.backends.base import MAILServerBackend

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 6
RETRY_DELAYS = (
    timedelta(seconds=1),
    timedelta(seconds=30),
    timedelta(minutes=5),
    timedelta(hours=1),
    timedelta(hours=6),
)
DEFAULT_RETRY_AFTER_CAP = timedelta(hours=24)
DEFAULT_RESPONSE_MAX_BYTES = 64 * 1024
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

AttemptDisposition = Literal["success", "retry", "permanent"]


@dataclass(frozen=True, slots=True)
class FederationHTTPResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes = b""


@dataclass(frozen=True, slots=True)
class FederationTransportError(RuntimeError):
    """A sanitized network failure with destination-reachability context."""

    category: str
    peer_reached: bool

    def __str__(self) -> str:
        return self.category


class OutboundDiscovery(Protocol):
    async def get_manifest(
        self, host: str, *, force_refresh: bool = False
    ) -> MAILFederationManifest: ...

    async def prepare_delivery_target(
        self, destination_host: str, delivery_url: str
    ) -> FederationDeliveryTarget: ...


class FederationTransport(Protocol):
    async def post(
        self,
        *,
        destination_host: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> FederationHTTPResponse: ...


@dataclass(frozen=True, slots=True)
class FederationDeadLetterEvent:
    delivery: OutboundFederationDelivery
    failure_code: str
    peer_code: str | None
    failed_recipients: tuple[str, ...]


DeadLetterHandler = Callable[[FederationDeadLetterEvent], Awaitable[None]]


async def _noop_dead_letter(_event: FederationDeadLetterEvent) -> None:
    """Phase 5 replaces this seam with durable DSN generation."""


def classify_http_status(status_code: int) -> AttemptDisposition:
    if status_code in {202, 409}:
        return "success"
    if status_code == 429 or (500 <= status_code <= 599 and status_code != 501):
        return "retry"
    return "permanent"


def retry_delay_for_attempt(completed_attempt_count: int) -> timedelta | None:
    """Return the delay after attempts 1..5; attempt 6 is terminal."""

    if not 1 <= completed_attempt_count <= MAX_ATTEMPTS:
        raise ValueError("completed attempt count must be between 1 and 6")
    if completed_attempt_count == MAX_ATTEMPTS:
        return None
    return RETRY_DELAYS[completed_attempt_count - 1]


def parse_retry_after(
    value: str | None,
    *,
    now: datetime,
    cap: timedelta = DEFAULT_RETRY_AFTER_CAP,
) -> timedelta | None:
    """Parse delta-seconds or HTTP-date and clamp a valid value to ``cap``."""

    if value is None or cap <= timedelta(0):
        return None
    stripped = value.strip()
    delay: timedelta
    if stripped.isascii() and stripped.isdigit():
        delay = timedelta(seconds=int(stripped))
    else:
        try:
            parsed = parsedate_to_datetime(stripped)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        delay = max(parsed.astimezone(UTC) - now.astimezone(UTC), timedelta(0))
    return min(delay, cap)


def _peer_error(response: FederationHTTPResponse) -> tuple[str | None, tuple[str, ...]]:
    try:
        value = json.loads(response.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, ()
    if not isinstance(value, dict):
        return None, ()
    code = value.get("code")
    if not isinstance(code, str) or _ERROR_CODE.fullmatch(code) is None:
        code = None
    recipients = value.get("failed_recipients")
    if not isinstance(recipients, list) or not all(
        isinstance(item, str) for item in recipients
    ):
        return code, ()
    return code, tuple(dict.fromkeys(recipients))


def _header(headers: Mapping[str, str], name: str) -> str | None:
    normalized = name.lower()
    return next(
        (value for key, value in headers.items() if key.lower() == normalized),
        None,
    )


def _permanent_failure_code(status_code: int, peer_code: str | None) -> str:
    if status_code == 413 or peer_code == "payload_too_large":
        return "payload_too_large"
    if peer_code == "policy_denied":
        return "policy_denied"
    if status_code == 404 and peer_code == "recipient_not_found":
        return "recipient_not_found"
    return "host_rejected"


def _attempt_delivery_id(envelope_id: str, attempt_number: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"mail-federation:{envelope_id}:{attempt_number}"))


class HTTPFederationTransport:
    """DNS-pinned HTTP transport that never follows peer redirects."""

    def __init__(
        self,
        *,
        discovery: OutboundDiscovery,
        connect_timeout_seconds: float = 3.0,
        read_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 10.0,
        max_response_bytes: int = DEFAULT_RESPONSE_MAX_BYTES,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.discovery = discovery
        self.total_timeout_seconds = total_timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
                write=read_timeout_seconds,
                pool=connect_timeout_seconds,
            ),
            follow_redirects=False,
            trust_env=False,
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def post(
        self,
        *,
        destination_host: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> FederationHTTPResponse:
        target = await self.discovery.prepare_delivery_target(destination_host, url)
        request_headers = httpx.Headers(headers)
        request_headers["Host"] = target.authority
        request = self._client.build_request(
            "POST",
            target.connection_url,
            headers=request_headers,
            content=body,
            extensions={"sni_hostname": target.sni_hostname},
        )
        response: httpx.Response | None = None
        try:
            async with asyncio.timeout(self.total_timeout_seconds):
                response = await self._client.send(
                    request,
                    stream=True,
                    follow_redirects=False,
                )
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self.max_response_bytes:
                        chunks = []
                        break
                    chunks.append(chunk)
                return FederationHTTPResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=b"".join(chunks),
                )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            raise FederationTransportError("connection_failed", False) from exc
        except httpx.RequestError as exc:
            raise FederationTransportError("request_failed", True) from exc
        except TimeoutError as exc:
            raise FederationTransportError("request_timed_out", False) from exc
        finally:
            if response is not None:
                await response.aclose()


class OutboundFederationService:
    """Execute and durably classify one already-leased outbound envelope."""

    def __init__(
        self,
        *,
        backend: MAILServerBackend,
        config: FederationConfig,
        discovery: OutboundDiscovery,
        transport: FederationTransport,
        dead_letter_handler: DeadLetterHandler = _noop_dead_letter,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        retry_after_cap: timedelta = DEFAULT_RETRY_AFTER_CAP,
        uuid_factory: Callable[[], object] = uuid4,
    ) -> None:
        self.backend = backend
        self.config = config
        self.discovery = discovery
        self.transport = transport
        self.dead_letter_handler = dead_letter_handler
        self.clock = clock
        self.retry_after_cap = retry_after_cap
        self.uuid_factory = uuid_factory

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("federation outbound clock must be timezone-aware")
        return value.astimezone(UTC)

    async def _emit_dead_letter(
        self,
        failed: OutboundFederationDelivery,
        *,
        failure_code: str,
        peer_code: str | None = None,
        failed_recipients: tuple[str, ...] = (),
    ) -> None:
        event = FederationDeadLetterEvent(
            delivery=failed,
            failure_code=failure_code,
            peer_code=peer_code,
            failed_recipients=failed_recipients
            or tuple(failed.envelope.message.recipients),
        )
        try:
            await self.dead_letter_handler(event)
        except Exception:
            logger.exception(
                "federation dead-letter handler failed: envelope_id=%s destination=%s",
                failed.envelope_id,
                failed.destination_host,
            )

    async def _dead_letter(
        self,
        delivery: OutboundFederationDelivery,
        *,
        lease_owner: str,
        completed_at: datetime,
        failure_code: str,
        http_status: int | None,
        diagnostic: str,
        peer_code: str | None = None,
        failed_recipients: tuple[str, ...] = (),
    ) -> OutboundFederationDelivery:
        failed = await self.backend.fail_federation_delivery(
            delivery.envelope_id,
            lease_owner=lease_owner,
            completed_at=completed_at,
            failure_code=failure_code,
            http_status=http_status,
            error=diagnostic,
        )
        await self._emit_dead_letter(
            failed,
            failure_code=failure_code,
            peer_code=peer_code,
            failed_recipients=failed_recipients,
        )
        return failed

    async def _retry_or_exhaust(
        self,
        delivery: OutboundFederationDelivery,
        *,
        lease_owner: str,
        completed_at: datetime,
        http_status: int | None,
        diagnostic: str,
        peer_reached: bool,
        retry_after: timedelta | None = None,
    ) -> OutboundFederationDelivery:
        completed_attempts = delivery.attempt_count + 1
        fallback = retry_delay_for_attempt(completed_attempts)
        if fallback is None:
            failure_code = (
                "delivery_expired"
                if delivery.peer_was_reached or peer_reached
                else "host_unreachable"
            )
            logger.info(
                "federation attempts exhausted: envelope_id=%s destination=%s "
                "attempt=%d failure_code=%s",
                delivery.envelope_id,
                delivery.destination_host,
                completed_attempts,
                failure_code,
            )
            return await self._dead_letter(
                delivery,
                lease_owner=lease_owner,
                completed_at=completed_at,
                failure_code=failure_code,
                http_status=http_status,
                diagnostic=diagnostic,
            )
        delay = retry_after if retry_after is not None else fallback
        next_attempt_at = completed_at + delay
        logger.info(
            "federation retry scheduled: envelope_id=%s destination=%s "
            "attempt=%d next_attempt_at=%s",
            delivery.envelope_id,
            delivery.destination_host,
            completed_attempts,
            next_attempt_at.isoformat(),
        )
        return await self.backend.record_federation_attempt(
            delivery.envelope_id,
            lease_owner=lease_owner,
            attempted_at=completed_at,
            next_attempt_at=next_attempt_at,
            http_status=http_status,
            error=diagnostic,
            peer_reached=peer_reached,
        )

    async def _partition_recipient_rejection(
        self,
        delivery: OutboundFederationDelivery,
        *,
        lease_owner: str,
        completed_at: datetime,
        http_status: int,
        diagnostic: str,
        failed_recipients: tuple[str, ...],
    ) -> OutboundFederationDelivery:
        failed_set = set(failed_recipients)
        remaining = [
            recipient
            for recipient in delivery.envelope.message.recipients
            if recipient not in failed_set
        ]
        if not remaining:
            return await self._dead_letter(
                delivery,
                lease_owner=lease_owner,
                completed_at=completed_at,
                failure_code="recipient_not_found",
                http_status=http_status,
                diagnostic=diagnostic,
                peer_code="recipient_not_found",
                failed_recipients=failed_recipients,
            )

        target_id = str(self.uuid_factory())
        envelope_id = str(self.uuid_factory())
        replacement_target = MessageDeliveryTarget(
            target_id=target_id,
            message_id=delivery.message_id,
            origin="outbound",
            kind="remote",
            destination_host=delivery.destination_host,
            recipients=remaining,
            created_at=completed_at,
            updated_at=completed_at,
        )
        replacement_envelope = delivery.envelope.model_copy(
            update={
                "message_id": envelope_id,
                "message": delivery.envelope.message.model_copy(
                    update={"recipients": remaining}
                ),
                "sent_at": completed_at,
            }
        )
        replacement_delivery = OutboundFederationDelivery(
            envelope_id=envelope_id,
            target_id=target_id,
            message_id=delivery.message_id,
            destination_host=delivery.destination_host,
            envelope=replacement_envelope,
            next_attempt_at=completed_at,
            created_at=completed_at,
            updated_at=completed_at,
        )
        failed = await self.backend.partition_federation_delivery(
            delivery.envelope_id,
            lease_owner=lease_owner,
            completed_at=completed_at,
            failure_code="recipient_not_found",
            http_status=http_status,
            error=diagnostic,
            replacement_target=replacement_target,
            replacement_delivery=replacement_delivery,
        )
        await self._emit_dead_letter(
            failed,
            failure_code="recipient_not_found",
            peer_code="recipient_not_found",
            failed_recipients=failed_recipients,
        )
        return failed

    async def process(
        self,
        delivery: OutboundFederationDelivery,
        *,
        lease_owner: str,
    ) -> OutboundFederationDelivery:
        started_at = self._now()
        attempt_number = delivery.attempt_count + 1
        try:
            manifest = await self.discovery.get_manifest(delivery.destination_host)
            delivery_url = str(manifest.delivery_url)
            public_url = httpx.URL(delivery_url)
            if (
                public_url.scheme != "https"
                or public_url.host is None
                or public_url.host.lower() != delivery.destination_host.lower()
            ):
                raise FederationDiscoveryError(
                    "manifest delivery URL is not owned by the destination"
                )
            signed = sign_federation_request(
                url=delivery_url,
                # The envelope ID remains stable, while sent_at describes this
                # forwarding attempt so retries still satisfy ingress freshness.
                envelope=delivery.envelope.model_copy(update={"sent_at": started_at}),
                signing_key=self.config.signing_key,
                created=started_at,
            )
            headers = dict(signed.headers)
            headers[FEDERATION_ATTEMPT_HEADER] = str(attempt_number)
            headers[FEDERATION_DELIVERY_ID_HEADER] = _attempt_delivery_id(
                delivery.envelope_id,
                attempt_number,
            )
            response = await self.transport.post(
                destination_host=delivery.destination_host,
                url=delivery_url,
                headers=headers,
                body=signed.body,
            )
        except FederationDiscoveryError:
            completed_at = self._now()
            logger.info(
                "federation attempt retryable: envelope_id=%s destination=%s "
                "attempt=%d response_class=discovery next=ladder",
                delivery.envelope_id,
                delivery.destination_host,
                attempt_number,
            )
            return await self._retry_or_exhaust(
                delivery,
                lease_owner=lease_owner,
                completed_at=completed_at,
                http_status=None,
                diagnostic="federation discovery failed",
                peer_reached=False,
            )
        except FederationTransportError as exc:
            completed_at = self._now()
            logger.info(
                "federation attempt retryable: envelope_id=%s destination=%s "
                "attempt=%d response_class=%s next=ladder",
                delivery.envelope_id,
                delivery.destination_host,
                attempt_number,
                exc.category,
            )
            return await self._retry_or_exhaust(
                delivery,
                lease_owner=lease_owner,
                completed_at=completed_at,
                http_status=None,
                diagnostic=exc.category,
                peer_reached=exc.peer_reached,
            )
        except Exception:
            completed_at = self._now()
            logger.exception(
                "internal federation attempt failure: envelope_id=%s destination=%s",
                delivery.envelope_id,
                delivery.destination_host,
            )
            return await self._dead_letter(
                delivery,
                lease_owner=lease_owner,
                completed_at=completed_at,
                failure_code="internal_error",
                http_status=None,
                diagnostic="internal federation delivery failure",
            )

        completed_at = self._now()
        disposition = classify_http_status(response.status_code)
        peer_code, failed_recipients = _peer_error(response)
        allowed_recipients = set(delivery.envelope.message.recipients)
        failed_recipients = tuple(
            recipient
            for recipient in failed_recipients
            if recipient in allowed_recipients
        )
        latency_ms = max(0.0, (completed_at - started_at).total_seconds() * 1000)
        if disposition == "success":
            completed = await self.backend.complete_federation_delivery(
                delivery.envelope_id,
                lease_owner=lease_owner,
                completed_at=completed_at,
                delivered_by=f"daemon:federation@{self.config.public_host}",
                http_status=response.status_code,
            )
            logger.info(
                "federation attempt succeeded: envelope_id=%s destination=%s "
                "attempt=%d status=%d latency_ms=%.1f",
                delivery.envelope_id,
                delivery.destination_host,
                attempt_number,
                response.status_code,
                latency_ms,
            )
            return completed

        diagnostic = f"peer returned HTTP {response.status_code}"
        if peer_code is not None:
            diagnostic += f" ({peer_code})"
        if disposition == "permanent":
            if (
                response.status_code == 404
                and peer_code == "recipient_not_found"
                and failed_recipients
            ):
                logger.info(
                    "federation recipient rejection partitioned: envelope_id=%s "
                    "destination=%s attempt=%d status=%d failed_count=%d "
                    "latency_ms=%.1f",
                    delivery.envelope_id,
                    delivery.destination_host,
                    attempt_number,
                    response.status_code,
                    len(failed_recipients),
                    latency_ms,
                )
                return await self._partition_recipient_rejection(
                    delivery,
                    lease_owner=lease_owner,
                    completed_at=completed_at,
                    http_status=response.status_code,
                    diagnostic=diagnostic,
                    failed_recipients=failed_recipients,
                )
            failure_code = _permanent_failure_code(response.status_code, peer_code)
            if failure_code == "recipient_not_found":
                # A peer may only partition addresses named in the signed
                # envelope. An empty/foreign set is an invalid host rejection.
                failure_code = "host_rejected"
            logger.info(
                "federation attempt dead-lettered: envelope_id=%s destination=%s "
                "attempt=%d status=%d failure_code=%s latency_ms=%.1f",
                delivery.envelope_id,
                delivery.destination_host,
                attempt_number,
                response.status_code,
                failure_code,
                latency_ms,
            )
            return await self._dead_letter(
                delivery,
                lease_owner=lease_owner,
                completed_at=completed_at,
                failure_code=failure_code,
                http_status=response.status_code,
                diagnostic=diagnostic,
                peer_code=peer_code,
                failed_recipients=failed_recipients,
            )

        retry_after = None
        if response.status_code in {429, 503}:
            retry_after = parse_retry_after(
                _header(response.headers, "Retry-After"),
                now=completed_at,
                cap=self.retry_after_cap,
            )
        logger.info(
            "federation attempt retryable: envelope_id=%s destination=%s "
            "attempt=%d status=%d latency_ms=%.1f next=%s",
            delivery.envelope_id,
            delivery.destination_host,
            attempt_number,
            response.status_code,
            latency_ms,
            "retry-after" if retry_after is not None else "ladder",
        )
        return await self._retry_or_exhaust(
            delivery,
            lease_owner=lease_owner,
            completed_at=completed_at,
            http_status=response.status_code,
            diagnostic=diagnostic,
            peer_reached=True,
            retry_after=retry_after,
        )
