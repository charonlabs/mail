# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Validated runtime configuration for MAIL Federation v1."""

from __future__ import annotations

import ipaddress
import math
import os
import ssl
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import httpx
from mail_protocol.core.federation import (
    MAILFederationManifest,
    MAILFederationPolicyHints,
    MAILFederationPublicKey,
)
from mail_protocol.core.user_agents import MAILDaemon
from mail_protocol.core.validators import validate_daemon_worker_name, validate_host
from mail_protocol.network.federation import FEDERATION_DELIVERY_PATH_V1
from pydantic import TypeAdapter, ValidationError

from mail_server.federation.discovery import (
    DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS,
    DEFAULT_DISCOVERY_TTL_SECONDS,
    MAX_DISCOVERY_TTL_SECONDS,
    MIN_DISCOVERY_TTL_SECONDS,
    FederationDiscoveryClient,
)
from mail_server.federation.keys import (
    FederationPrivateKey,
    load_federation_private_key,
)

if TYPE_CHECKING:
    from mail_server.backends.base import MAILServerBackend
    from mail_server.federation.outbound import HTTPFederationTransport
    from mail_server.federation.worker import FederationWorker

FederationPolicy = Literal["open", "allowlist", "closed"]
DEFAULT_MAX_REQUEST_BYTES = 1024 * 1024


class FederationConfigurationError(ValueError):
    """Raised when enabled federation would start in an unsafe state."""


def _boolean(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise FederationConfigurationError(f"{name} must be a boolean")


def _integer(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise FederationConfigurationError(f"{name} must be an integer") from exc


def _float(name: str, *, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise FederationConfigurationError(f"{name} must be a number") from exc
    if not math.isfinite(value):
        raise FederationConfigurationError(f"{name} must be a finite number")
    return value


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise FederationConfigurationError(
            f"{name} is required when federation is enabled"
        )
    return value.strip()


def _normalize_host(value: str, *, allow_private_hosts: bool) -> str:
    try:
        validate_host(value)
        normalized = value.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise FederationConfigurationError(
            "MAIL_FEDERATION_PUBLIC_HOST is invalid"
        ) from exc
    if allow_private_hosts:
        return normalized
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        if "." not in normalized:
            raise FederationConfigurationError(
                "production federation requires a multi-label DNS hostname"
            )
    else:
        raise FederationConfigurationError(
            "production federation requires a DNS hostname"
        )
    return normalized


def _overlap_public_keys() -> tuple[MAILFederationPublicKey, ...]:
    raw = os.getenv("MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS")
    file_name = os.getenv("MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS_FILE")
    if raw and raw.strip() and file_name and file_name.strip():
        raise FederationConfigurationError(
            "set only one of MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS and "
            "MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS_FILE"
        )
    if file_name and file_name.strip():
        try:
            raw = Path(file_name.strip()).read_text(encoding="utf-8")
        except OSError as exc:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS_FILE is not readable"
            ) from exc
    if raw is None or not raw.strip():
        return ()
    try:
        values = TypeAdapter(list[MAILFederationPublicKey]).validate_json(raw)
    except ValidationError as exc:
        raise FederationConfigurationError(
            "MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS must be a JSON array of public keys"
        ) from exc
    return tuple(values)


def _tls_context(ca_file: Path | None) -> ssl.SSLContext | bool:
    if ca_file is None:
        return True
    try:
        return ssl.create_default_context(cafile=str(ca_file))
    except OSError as exc:
        raise FederationConfigurationError(
            "MAIL_FEDERATION_CA_FILE must contain a readable CA certificate"
        ) from exc


@dataclass(frozen=True, slots=True)
class FederationConfig:
    """All validated state needed by signed ingress and future egress."""

    public_host: str
    delivery_url: str
    signing_key: FederationPrivateKey
    public_keys: tuple[MAILFederationPublicKey, ...]
    policy: FederationPolicy
    allowlist: frozenset[str]
    discovery_ttl_seconds: int
    max_request_bytes: int
    allow_private_hosts: bool = False
    allow_insecure_transport: bool = False
    outbound_connect_timeout_seconds: float = 3.0
    outbound_read_timeout_seconds: float = 5.0
    outbound_total_timeout_seconds: float = 10.0
    outbound_response_max_bytes: int = 64 * 1024
    discovery_connect_timeout_seconds: float = 3.0
    discovery_read_timeout_seconds: float = 5.0
    discovery_total_timeout_seconds: float = DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS
    discovery_response_max_bytes: int = 64 * 1024
    discovery_port: int = 443
    ca_file: Path | None = None
    worker_poll_interval_seconds: float = 1.0
    worker_batch_size: int = 20
    worker_lease_seconds: float = 30.0
    retry_after_cap_seconds: int = 24 * 60 * 60
    bounce_worker_name: str = "bounces"
    bounce_rate_limit: int = 100
    test_retry_delays_seconds: tuple[float, ...] | None = None

    @property
    def manifest(self) -> MAILFederationManifest:
        return MAILFederationManifest(
            protocol_version="1",
            mail_protocol_version="2.0",
            delivery_url=self.delivery_url,
            public_keys=list(self.public_keys),
            policy_hints=MAILFederationPolicyHints(accepts=self.policy),
        )

    @classmethod
    def from_env(cls) -> FederationConfig | None:
        """Return ``None`` when disabled; otherwise validate every ingress value."""

        if not _boolean("MAIL_FEDERATION_ENABLED"):
            return None

        allow_private = _boolean("MAIL_FEDERATION_ALLOW_PRIVATE_HOSTS")
        public_host = _normalize_host(
            _required("MAIL_FEDERATION_PUBLIC_HOST"),
            allow_private_hosts=allow_private,
        )
        delivery_url = _required("MAIL_FEDERATION_DELIVERY_URL")
        try:
            parsed_url = httpx.URL(delivery_url)
        except httpx.InvalidURL as exc:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_DELIVERY_URL is invalid"
            ) from exc
        if (
            parsed_url.scheme != "https"
            or parsed_url.host is None
            or parsed_url.userinfo
            or parsed_url.fragment
            or parsed_url.query
            or parsed_url.path != FEDERATION_DELIVERY_PATH_V1
        ):
            raise FederationConfigurationError(
                "MAIL_FEDERATION_DELIVERY_URL must be the canonical absolute HTTPS "
                "Federation v1 endpoint without query, userinfo, or fragment"
            )
        if parsed_url.host.encode("idna").decode("ascii").lower() != public_host:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_DELIVERY_URL host must match "
                "MAIL_FEDERATION_PUBLIC_HOST"
            )

        policy_value = _required("MAIL_FEDERATION_POLICY").lower()
        if policy_value not in {"open", "allowlist", "closed"}:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_POLICY must be open, allowlist, or closed"
            )
        policy = cast(FederationPolicy, policy_value)
        allowlist = frozenset(
            _normalize_host(item.strip(), allow_private_hosts=allow_private)
            for item in os.getenv("MAIL_FEDERATION_ALLOWLIST", "").split(",")
            if item.strip()
        )
        if policy == "allowlist" and not allowlist:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_ALLOWLIST is required for allowlist policy"
            )

        ttl = _integer(
            "MAIL_FEDERATION_DISCOVERY_TTL_SECONDS",
            default=DEFAULT_DISCOVERY_TTL_SECONDS,
        )
        if not MIN_DISCOVERY_TTL_SECONDS <= ttl <= MAX_DISCOVERY_TTL_SECONDS:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_DISCOVERY_TTL_SECONDS must be between 300 and 900"
            )
        max_request_bytes = _integer(
            "MAIL_FEDERATION_MAX_REQUEST_BYTES",
            default=DEFAULT_MAX_REQUEST_BYTES,
        )
        if max_request_bytes <= 0:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_MAX_REQUEST_BYTES must be positive"
            )

        connect_timeout = _float("MAIL_FEDERATION_CONNECT_TIMEOUT_SECONDS", default=3.0)
        read_timeout = _float("MAIL_FEDERATION_READ_TIMEOUT_SECONDS", default=5.0)
        total_timeout = _float("MAIL_FEDERATION_TOTAL_TIMEOUT_SECONDS", default=10.0)
        response_max_bytes = _integer(
            "MAIL_FEDERATION_MAX_RESPONSE_BYTES", default=64 * 1024
        )
        discovery_connect_timeout = _float(
            "MAIL_FEDERATION_DISCOVERY_CONNECT_TIMEOUT_SECONDS", default=3.0
        )
        discovery_read_timeout = _float(
            "MAIL_FEDERATION_DISCOVERY_READ_TIMEOUT_SECONDS", default=5.0
        )
        discovery_total_timeout = _float(
            "MAIL_FEDERATION_DISCOVERY_TOTAL_TIMEOUT_SECONDS",
            default=DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS,
        )
        discovery_response_max_bytes = _integer(
            "MAIL_FEDERATION_DISCOVERY_MAX_RESPONSE_BYTES", default=64 * 1024
        )
        discovery_port = _integer(
            "MAIL_FEDERATION_TEST_DISCOVERY_PORT", default=443
        )
        if not 1 <= discovery_port <= 65535:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_TEST_DISCOVERY_PORT must be between 1 and 65535"
            )
        if discovery_port != 443 and not allow_private:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_TEST_DISCOVERY_PORT requires the private-host test override"
            )
        ca_file_raw = os.getenv("MAIL_FEDERATION_CA_FILE")
        ca_file = Path(ca_file_raw.strip()) if ca_file_raw and ca_file_raw.strip() else None
        if ca_file is not None:
            _tls_context(ca_file)
        poll_interval = _float("MAIL_FEDERATION_WORKER_POLL_SECONDS", default=1.0)
        batch_size = _integer("MAIL_FEDERATION_WORKER_BATCH_SIZE", default=20)
        lease_seconds = _float("MAIL_FEDERATION_WORKER_LEASE_SECONDS", default=30.0)
        retry_after_cap = _integer(
            "MAIL_FEDERATION_RETRY_AFTER_CAP_SECONDS", default=24 * 60 * 60
        )
        bounce_worker_name = os.getenv(
            "MAIL_FEDERATION_BOUNCE_DAEMON", "bounces"
        ).strip()
        try:
            validate_daemon_worker_name(bounce_worker_name)
        except ValueError as exc:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_BOUNCE_DAEMON must be a valid daemon worker name"
            ) from exc
        bounce_rate_limit = _integer("MAIL_FEDERATION_BOUNCE_RATE_LIMIT", default=100)
        retry_delays_raw = os.getenv("MAIL_FEDERATION_TEST_RETRY_DELAYS_SECONDS")
        test_retry_delays: tuple[float, ...] | None = None
        if retry_delays_raw and retry_delays_raw.strip():
            try:
                test_retry_delays = tuple(
                    float(value.strip()) for value in retry_delays_raw.split(",")
                )
            except ValueError as exc:
                raise FederationConfigurationError(
                    "MAIL_FEDERATION_TEST_RETRY_DELAYS_SECONDS must contain numbers"
                ) from exc
            if (
                len(test_retry_delays) != 5
                or any(
                    not math.isfinite(value) or value <= 0
                    for value in test_retry_delays
                )
                or not allow_private
            ):
                raise FederationConfigurationError(
                    "MAIL_FEDERATION_TEST_RETRY_DELAYS_SECONDS requires the "
                    "private-host test override and five positive finite values"
                )
        if (
            min(
                connect_timeout,
                read_timeout,
                total_timeout,
                discovery_connect_timeout,
                discovery_read_timeout,
                discovery_total_timeout,
            )
            <= 0
        ):
            raise FederationConfigurationError(
                "federation discovery and outbound timeouts must be positive"
            )
        if (
            response_max_bytes <= 0
            or discovery_response_max_bytes <= 0
            or poll_interval <= 0
            or batch_size <= 0
        ):
            raise FederationConfigurationError(
                "federation response limits, poll interval, and batch size must be positive"
            )
        if lease_seconds <= total_timeout + discovery_total_timeout:
            raise FederationConfigurationError(
                "federation worker lease must exceed discovery plus the outbound "
                "total timeout"
            )
        if retry_after_cap <= 0 or bounce_rate_limit <= 0:
            raise FederationConfigurationError(
                "federation Retry-After cap and bounce rate limit must be positive"
            )

        key = load_federation_private_key(
            Path(_required("MAIL_FEDERATION_PRIVATE_KEY_FILE")),
            key_id=_required("MAIL_FEDERATION_KEY_ID"),
            expected_public_key=os.getenv("MAIL_FEDERATION_PUBLIC_KEY") or None,
        )
        overlap = _overlap_public_keys()
        public_keys = (key.manifest_key(), *overlap)
        key_ids = [item.key_id for item in public_keys]
        if len(key_ids) != len(set(key_ids)):
            raise FederationConfigurationError(
                "active and overlap federation key IDs must be unique"
            )

        return cls(
            public_host=public_host,
            delivery_url=str(parsed_url),
            signing_key=key,
            public_keys=public_keys,
            policy=policy,
            allowlist=allowlist,
            discovery_ttl_seconds=ttl,
            max_request_bytes=max_request_bytes,
            allow_private_hosts=allow_private,
            allow_insecure_transport=_boolean(
                "MAIL_FEDERATION_ALLOW_INSECURE_TRANSPORT"
            ),
            outbound_connect_timeout_seconds=connect_timeout,
            outbound_read_timeout_seconds=read_timeout,
            outbound_total_timeout_seconds=total_timeout,
            outbound_response_max_bytes=response_max_bytes,
            discovery_connect_timeout_seconds=discovery_connect_timeout,
            discovery_read_timeout_seconds=discovery_read_timeout,
            discovery_total_timeout_seconds=discovery_total_timeout,
            discovery_response_max_bytes=discovery_response_max_bytes,
            discovery_port=discovery_port,
            ca_file=ca_file,
            worker_poll_interval_seconds=poll_interval,
            worker_batch_size=batch_size,
            worker_lease_seconds=lease_seconds,
            retry_after_cap_seconds=retry_after_cap,
            bounce_worker_name=bounce_worker_name,
            bounce_rate_limit=bounce_rate_limit,
            test_retry_delays_seconds=test_retry_delays,
        )


@dataclass(slots=True)
class FederationRuntime:
    """Lifespan-owned federation services."""

    config: FederationConfig | None
    discovery: FederationDiscoveryClient | None
    transport: HTTPFederationTransport | None = None
    worker: FederationWorker | None = None

    @classmethod
    def from_env(cls, *, local_host: str | None = None) -> FederationRuntime:
        config = FederationConfig.from_env()
        if config is None:
            return cls(config=None, discovery=None)
        if local_host is not None and config.public_host.lower() != local_host.lower():
            raise FederationConfigurationError(
                "MAIL_FEDERATION_PUBLIC_HOST must match the server's MAIL_HOST"
            )
        return cls.from_config(config)

    @classmethod
    def from_config(cls, config: FederationConfig | None) -> FederationRuntime:
        """Build lifespan services from already-validated configuration."""

        if config is None:
            return cls(config=None, discovery=None)
        return cls(
            config=config,
            discovery=FederationDiscoveryClient(
                ttl_seconds=config.discovery_ttl_seconds,
                connect_timeout_seconds=config.discovery_connect_timeout_seconds,
                read_timeout_seconds=config.discovery_read_timeout_seconds,
                total_timeout_seconds=config.discovery_total_timeout_seconds,
                max_response_bytes=config.discovery_response_max_bytes,
                discovery_port=config.discovery_port,
                allow_private_hosts=config.allow_private_hosts,
                verify=_tls_context(config.ca_file),
            ),
        )

    @property
    def enabled(self) -> bool:
        return self.config is not None

    async def start(self, backend: MAILServerBackend) -> None:
        if self.config is None or self.discovery is None:
            return
        from mail_server.federation.outbound import (
            HTTPFederationTransport,
            OutboundFederationService,
        )
        from mail_server.federation.worker import FederationWorker

        bounce_address = (
            f"daemon:{self.config.bounce_worker_name}@{self.config.public_host}"
        )
        try:
            bounce_user_agent = await backend.get_user_agent(bounce_address)
        except ValueError as exc:
            raise FederationConfigurationError(
                f"configured federation bounce daemon does not exist: {bounce_address}"
            ) from exc
        bounce_daemon = bounce_user_agent.user_agent
        if not isinstance(bounce_daemon, MAILDaemon) or (
            "bounce:emit" not in bounce_daemon.scopes
        ):
            raise FederationConfigurationError(
                "configured federation bounce daemon must carry bounce:emit"
            )
        await backend.configure_bounce_delivery(
            emitter=bounce_daemon,
            rate_limit=self.config.bounce_rate_limit,
        )

        self.transport = HTTPFederationTransport(
            discovery=self.discovery,
            connect_timeout_seconds=self.config.outbound_connect_timeout_seconds,
            read_timeout_seconds=self.config.outbound_read_timeout_seconds,
            total_timeout_seconds=self.config.outbound_total_timeout_seconds,
            max_response_bytes=self.config.outbound_response_max_bytes,
            verify=_tls_context(self.config.ca_file),
        )
        outbound = OutboundFederationService(
            backend=backend,
            config=self.config,
            discovery=self.discovery,
            transport=self.transport,
            retry_after_cap=timedelta(seconds=self.config.retry_after_cap_seconds),
            bounce_emitter=bounce_daemon,
            bounce_rate_limit=self.config.bounce_rate_limit,
            retry_delays=(
                tuple(
                    timedelta(seconds=value)
                    for value in self.config.test_retry_delays_seconds
                )
                if self.config.test_retry_delays_seconds is not None
                else None
            ),
        )
        self.worker = FederationWorker(
            backend=backend,
            outbound=outbound,
            poll_interval_seconds=self.config.worker_poll_interval_seconds,
            batch_size=self.config.worker_batch_size,
            lease_duration=timedelta(seconds=self.config.worker_lease_seconds),
        )
        self.worker.start()

    async def aclose(self) -> None:
        if self.worker is not None:
            await self.worker.stop()
            self.worker = None
        if self.transport is not None:
            await self.transport.aclose()
            self.transport = None
        if self.discovery is not None:
            await self.discovery.aclose()


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """Validated server identity and optional federation configuration."""

    local_host: str
    federation: FederationConfig | None

    @classmethod
    def from_env(cls) -> ServerSettings:
        raw_host = os.getenv("MAIL_HOST")
        if raw_host is None or not raw_host.strip():
            raise FederationConfigurationError("MAIL_HOST is required")
        raw_host = raw_host.strip()
        try:
            validate_host(raw_host)
            local_host = raw_host.encode("idna").decode("ascii").lower()
        except (UnicodeError, ValueError) as exc:
            raise FederationConfigurationError("MAIL_HOST is invalid") from exc
        federation = FederationConfig.from_env()
        if federation is not None and federation.public_host != local_host:
            raise FederationConfigurationError(
                "MAIL_FEDERATION_PUBLIC_HOST must match the server's MAIL_HOST"
            )
        return cls(local_host=local_host, federation=federation)
