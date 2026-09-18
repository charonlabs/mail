# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""HTTPS discovery with bounded caching and DNS-pinned SSRF defenses."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from time import monotonic

import httpx
from mail_protocol.core.federation import (
    MAILFederationManifest,
    MAILFederationPublicKey,
)
from mail_protocol.core.validators import validate_host
from mail_protocol.network.federation import FEDERATION_DISCOVERY_PATH
from pydantic import ValidationError

DEFAULT_DISCOVERY_TTL_SECONDS = 600
MIN_DISCOVERY_TTL_SECONDS = 300
MAX_DISCOVERY_TTL_SECONDS = 900
DEFAULT_DISCOVERY_MAX_BYTES = 64 * 1024
DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS = 8.0

HostResolver = Callable[[str, int], Awaitable[Sequence[str]]]
MonotonicClock = Callable[[], float]


class FederationDiscoveryError(RuntimeError):
    """Base class for safe discovery failures."""


class FederationHostRejected(FederationDiscoveryError):
    """Raised when a destination is not safe for production federation."""


class FederationManifestError(FederationDiscoveryError):
    """Raised when a peer returns an invalid discovery document."""


class FederationUnknownKey(FederationDiscoveryError):
    """Raised when a peer does not advertise a requested key ID."""


@dataclass(frozen=True, slots=True)
class ResolvedFederationKey:
    """A public key plus whether it came from a pre-existing cache entry."""

    key: MAILFederationPublicKey
    manifest_from_cache: bool


@dataclass(frozen=True, slots=True)
class FederationDeliveryTarget:
    """A validated public URL and its immediately resolved connection target."""

    public_url: str
    connection_url: str
    authority: str
    sni_hostname: str


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    manifest: MAILFederationManifest
    expires_at: float


async def _system_resolver(host: str, port: int) -> Sequence[str]:
    loop = asyncio.get_running_loop()
    try:
        answers = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except OSError as exc:
        raise FederationDiscoveryError("federation host DNS lookup failed") from exc
    return tuple(dict.fromkeys(answer[4][0] for answer in answers))


class FederationDiscoveryClient:
    """Fetch and cache validated federation manifests without DNS rebinding."""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_DISCOVERY_TTL_SECONDS,
        connect_timeout_seconds: float = 3.0,
        read_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_DISCOVERY_MAX_BYTES,
        allow_private_hosts: bool = False,
        resolver: HostResolver = _system_resolver,
        client: httpx.AsyncClient | None = None,
        clock: MonotonicClock = monotonic,
    ) -> None:
        if not MIN_DISCOVERY_TTL_SECONDS <= ttl_seconds <= MAX_DISCOVERY_TTL_SECONDS:
            raise ValueError("discovery TTL must be between 300 and 900 seconds")
        if (
            min(
                connect_timeout_seconds,
                read_timeout_seconds,
                total_timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("discovery timeouts must be positive")
        if max_response_bytes <= 0:
            raise ValueError("discovery response limit must be positive")

        self.ttl_seconds = ttl_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds
        self.total_timeout_seconds = total_timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.allow_private_hosts = allow_private_hosts
        self.resolver = resolver
        self.clock = clock
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
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> FederationDiscoveryClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def invalidate(self, host: str) -> None:
        """Evict one host, normally before a key-rotation refresh."""

        self._cache.pop(self._normalize_host(host), None)

    def _normalize_host(self, host: str) -> str:
        try:
            validate_host(host)
            normalized = host.encode("idna").decode("ascii").lower()
        except (UnicodeError, ValueError) as exc:
            raise FederationHostRejected("invalid federation hostname") from exc
        if not self.allow_private_hosts:
            try:
                ipaddress.ip_address(normalized)
            except ValueError:
                pass
            else:
                raise FederationHostRejected(
                    "production federation requires a DNS hostname"
                )
            if "." not in normalized:
                raise FederationHostRejected(
                    "production federation requires a multi-label DNS hostname"
                )
        return normalized

    async def _validated_addresses(self, host: str, port: int) -> tuple[str, ...]:
        normalized = self._normalize_host(host)
        try:
            values = tuple(dict.fromkeys(await self.resolver(normalized, port)))
        except FederationDiscoveryError:
            raise
        except Exception as exc:
            raise FederationDiscoveryError("federation host DNS lookup failed") from exc
        if not values:
            raise FederationDiscoveryError("federation host has no usable addresses")

        addresses: list[str] = []
        for value in values:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as exc:
                raise FederationDiscoveryError(
                    "federation DNS returned an invalid address"
                ) from exc
            if not self.allow_private_hosts and not address.is_global:
                raise FederationHostRejected(
                    "federation host resolved to a non-public address"
                )
            addresses.append(address.compressed)
        return tuple(addresses)

    async def _fetch(self, host: str) -> MAILFederationManifest:
        # Resolve first, validate every answer, then connect to one of those exact
        # addresses while retaining the DNS name for Host and TLS verification.
        addresses = await self._validated_addresses(host, 443)
        pinned_url = httpx.URL(
            scheme="https",
            host=addresses[0],
            port=443,
            path=FEDERATION_DISCOVERY_PATH,
        )
        request = self._client.build_request(
            "GET",
            pinned_url,
            headers={"Accept": "application/json", "Host": host},
            extensions={
                "sni_hostname": host,
                "timeout": {
                    "connect": self.connect_timeout_seconds,
                    "read": self.read_timeout_seconds,
                    "write": self.read_timeout_seconds,
                    "pool": self.connect_timeout_seconds,
                },
            },
        )
        response: httpx.Response | None = None
        try:
            async with asyncio.timeout(self.total_timeout_seconds):
                response = await self._client.send(
                    request,
                    stream=True,
                    follow_redirects=False,
                )
                if response.is_redirect:
                    raise FederationManifestError(
                        "federation discovery redirects are not allowed"
                    )
                if response.status_code != 200:
                    raise FederationManifestError(
                        "federation discovery did not return HTTP 200"
                    )
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise FederationManifestError(
                        "federation manifest must use application/json"
                    )
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError as exc:
                        raise FederationManifestError(
                            "federation manifest has an invalid Content-Length"
                        ) from exc
                    if declared_size < 0 or declared_size > self.max_response_bytes:
                        raise FederationManifestError(
                            "federation manifest exceeds the response limit"
                        )

                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self.max_response_bytes:
                        raise FederationManifestError(
                            "federation manifest exceeds the response limit"
                        )
                    chunks.append(chunk)
        except TimeoutError as exc:
            raise FederationDiscoveryError("federation discovery timed out") from exc
        except httpx.HTTPError as exc:
            raise FederationDiscoveryError(
                "federation discovery request failed"
            ) from exc
        finally:
            if response is not None:
                await response.aclose()

        try:
            payload = json.loads(b"".join(chunks))
            manifest = MAILFederationManifest.model_validate(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
            raise FederationManifestError("invalid federation manifest") from exc

        delivery_url = httpx.URL(str(manifest.delivery_url))
        if delivery_url.userinfo or delivery_url.fragment or not delivery_url.host:
            raise FederationManifestError(
                "federation delivery URL must not contain userinfo or a fragment"
            )
        # Validate the advertised target now; the outbound transport must repeat
        # this resolution and pin its own connection immediately before sending.
        await self._validated_addresses(
            delivery_url.host,
            delivery_url.port or 443,
        )
        return manifest

    async def _manifest_with_source(
        self,
        host: str,
        *,
        force_refresh: bool = False,
    ) -> tuple[MAILFederationManifest, bool]:
        normalized = self._normalize_host(host)
        now = self.clock()
        if not force_refresh:
            cached = self._cache.get(normalized)
            if cached is not None and cached.expires_at > now:
                return cached.manifest, True

        async with self._lock:
            now = self.clock()
            if not force_refresh:
                cached = self._cache.get(normalized)
                if cached is not None and cached.expires_at > now:
                    return cached.manifest, True
            manifest = await self._fetch(normalized)
            self._cache[normalized] = _CacheEntry(
                manifest=manifest,
                expires_at=self.clock() + self.ttl_seconds,
            )
            return manifest, False

    async def get_manifest(
        self,
        host: str,
        *,
        force_refresh: bool = False,
    ) -> MAILFederationManifest:
        manifest, _ = await self._manifest_with_source(
            host,
            force_refresh=force_refresh,
        )
        return manifest

    async def prepare_delivery_target(
        self,
        destination_host: str,
        delivery_url: str,
    ) -> FederationDeliveryTarget:
        """Revalidate ownership/DNS immediately before an outbound connection."""

        normalized_destination = self._normalize_host(destination_host)
        try:
            public_url = httpx.URL(delivery_url)
        except httpx.InvalidURL as exc:
            raise FederationManifestError("invalid federation delivery URL") from exc
        if (
            public_url.scheme != "https"
            or public_url.host is None
            or public_url.userinfo
            or public_url.fragment
        ):
            raise FederationManifestError(
                "federation delivery URL must be an absolute HTTPS URL"
            )
        normalized_target = self._normalize_host(public_url.host)
        if normalized_target != normalized_destination:
            raise FederationManifestError(
                "federation delivery URL is not owned by the destination host"
            )

        addresses = await self._validated_addresses(
            normalized_target,
            public_url.port or 443,
        )
        connection_url = public_url.copy_with(host=addresses[0])
        return FederationDeliveryTarget(
            public_url=str(public_url),
            connection_url=str(connection_url),
            authority=public_url.netloc.decode("ascii"),
            sni_hostname=normalized_target,
        )

    @staticmethod
    def _find_key(
        manifest: MAILFederationManifest,
        key_id: str,
    ) -> MAILFederationPublicKey | None:
        return next((key for key in manifest.public_keys if key.key_id == key_id), None)

    async def resolve_public_key(
        self,
        host: str,
        key_id: str,
    ) -> ResolvedFederationKey:
        """Resolve a key, refreshing once when a cached manifest misses it."""

        manifest, from_cache = await self._manifest_with_source(host)
        key = self._find_key(manifest, key_id)
        if key is None and from_cache:
            manifest, from_cache = await self._manifest_with_source(
                host,
                force_refresh=True,
            )
            key = self._find_key(manifest, key_id)
        if key is None:
            raise FederationUnknownKey("origin does not advertise the signature key")
        return ResolvedFederationKey(key=key, manifest_from_cache=from_cache)

    async def refresh_public_key(
        self,
        host: str,
        key_id: str,
    ) -> ResolvedFederationKey:
        """Force one manifest refresh after a cached signature fails."""

        manifest, _ = await self._manifest_with_source(host, force_refresh=True)
        key = self._find_key(manifest, key_id)
        if key is None:
            raise FederationUnknownKey("origin does not advertise the signature key")
        return ResolvedFederationKey(key=key, manifest_from_cache=False)
