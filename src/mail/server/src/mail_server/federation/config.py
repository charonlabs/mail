# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Validated runtime configuration for MAIL Federation v1."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import httpx
from mail_protocol.core.federation import (
    MAILFederationManifest,
    MAILFederationPolicyHints,
    MAILFederationPublicKey,
)
from mail_protocol.core.validators import validate_host
from mail_protocol.network.federation import FEDERATION_DELIVERY_PATH_V1
from pydantic import TypeAdapter, ValidationError

from mail_server.federation.discovery import (
    DEFAULT_DISCOVERY_TTL_SECONDS,
    MAX_DISCOVERY_TTL_SECONDS,
    MIN_DISCOVERY_TTL_SECONDS,
    FederationDiscoveryClient,
)
from mail_server.federation.keys import (
    FederationPrivateKey,
    load_federation_private_key,
)

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
    if raw is None or not raw.strip():
        return ()
    try:
        values = TypeAdapter(list[MAILFederationPublicKey]).validate_json(raw)
    except ValidationError as exc:
        raise FederationConfigurationError(
            "MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS must be a JSON array of public keys"
        ) from exc
    return tuple(values)


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
        )


@dataclass(slots=True)
class FederationRuntime:
    """Lifespan-owned federation services."""

    config: FederationConfig | None
    discovery: FederationDiscoveryClient | None

    @classmethod
    def from_env(cls, *, local_host: str | None = None) -> FederationRuntime:
        config = FederationConfig.from_env()
        if config is None:
            return cls(config=None, discovery=None)
        if local_host is not None and config.public_host.lower() != local_host.lower():
            raise FederationConfigurationError(
                "MAIL_FEDERATION_PUBLIC_HOST must match the server's MAIL_HOST"
            )
        return cls(
            config=config,
            discovery=FederationDiscoveryClient(
                ttl_seconds=config.discovery_ttl_seconds,
                allow_private_hosts=config.allow_private_hosts,
            ),
        )

    @property
    def enabled(self) -> bool:
        return self.config is not None

    async def aclose(self) -> None:
        if self.discovery is not None:
            await self.discovery.aclose()
