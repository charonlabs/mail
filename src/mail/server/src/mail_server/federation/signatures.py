# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""MAIL's strict RFC 9421 profile and exact-body digest handling."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from typing import Protocol

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from http_message_signatures import (
    HTTPMessageSigner,
    HTTPMessageVerifier,
    HTTPSignatureKeyResolver,
    algorithms,
    http_sfv,
)
from http_message_signatures.exceptions import (
    HTTPMessageSignaturesException,
    InvalidSignature,
)
from mail_protocol.core.federation import (
    MAILFederationPublicKey,
    MAILInterServerMessage,
)

from mail_server.federation.keys import (
    FederationPrivateKey,
    public_key_from_manifest,
)

FEDERATION_COVERED_COMPONENTS = (
    "@method",
    "@target-uri",
    "@authority",
    "content-digest",
    "date",
    "content-type",
)
FEDERATION_SIGNATURE_MAX_AGE = timedelta(minutes=5)
FEDERATION_CLOCK_SKEW = timedelta(seconds=5)
FEDERATION_SIGNATURE_LABEL = "sig1"

_CONTENT_DIGEST_RE = re.compile(r"^sha-256=:([A-Za-z0-9+/]+={0,2}):$")
_REQUIRED_SIGNATURE_PARAMETERS = {"alg", "created", "keyid"}
_SINGLETON_HEADERS = (
    "content-digest",
    "content-type",
    "date",
    "signature",
    "signature-input",
)

HeaderInput = (
    httpx.Headers
    | Mapping[str, str]
    | Sequence[tuple[str, str]]
    | Sequence[tuple[bytes, bytes]]
)


class FederationSignatureError(ValueError):
    """Raised when a request does not satisfy MAIL's signature profile."""


class FederationCryptographicSignatureError(FederationSignatureError):
    """Raised only after the request reaches public-key verification."""


@dataclass(frozen=True, slots=True)
class SignedFederationRequest:
    """The exact bytes and headers that an HTTP client must transmit."""

    method: str
    url: str
    headers: httpx.Headers
    body: bytes


@dataclass(frozen=True, slots=True)
class VerifiedFederationSignature:
    """Authenticated signature metadata safe for ingress decisions."""

    key_id: str
    created: datetime
    covered_components: frozenset[str]


class _ResolvedKey(Protocol):
    key: MAILFederationPublicKey
    manifest_from_cache: bool


class _DiscoveryResolver(Protocol):
    async def resolve_public_key(self, host: str, key_id: str) -> _ResolvedKey: ...

    async def refresh_public_key(self, host: str, key_id: str) -> _ResolvedKey: ...


class _StaticKeyResolver(HTTPSignatureKeyResolver):
    def __init__(
        self,
        *,
        key_id: str,
        private_key: object | None = None,
        public_key: object | None = None,
    ) -> None:
        self.key_id = key_id
        self.private_key = private_key
        self.public_key = public_key

    def _require_key_id(self, key_id: str) -> None:
        if not hmac.compare_digest(key_id, self.key_id):
            raise InvalidSignature("signature key ID is not the expected key")

    def resolve_private_key(self, key_id: str) -> object:
        self._require_key_id(key_id)
        if self.private_key is None:
            raise InvalidSignature("private key is unavailable")
        return self.private_key

    def resolve_public_key(self, key_id: str) -> object:
        self._require_key_id(key_id)
        if self.public_key is None:
            raise InvalidSignature("public key is unavailable")
        return self.public_key


def serialize_federation_envelope(envelope: MAILInterServerMessage) -> bytes:
    """Serialize an envelope once as deterministic, compact UTF-8 JSON."""

    return json.dumps(
        envelope.model_dump(mode="json", round_trip=True),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def content_digest(body: bytes) -> str:
    """Return the RFC 9530 SHA-256 dictionary value for exact body bytes."""

    digest = base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")
    return f"sha-256=:{digest}:"


def _validate_request_url(url: str) -> None:
    parsed = httpx.URL(url)
    if parsed.scheme != "https":
        raise FederationSignatureError("federation requests must use HTTPS")
    if not parsed.host or parsed.userinfo or parsed.fragment:
        raise FederationSignatureError(
            "federation request URL must not contain userinfo or a fragment"
        )


def sign_federation_request(
    *,
    url: str,
    envelope: MAILInterServerMessage,
    signing_key: FederationPrivateKey,
    created: datetime | None = None,
) -> SignedFederationRequest:
    """Serialize and sign one Federation v1 POST without copying its body."""

    _validate_request_url(url)
    signing_time = created or datetime.now(UTC)
    if signing_time.tzinfo is None or signing_time.utcoffset() is None:
        raise FederationSignatureError("signature creation time must be timezone-aware")
    signing_time = signing_time.astimezone(UTC)

    body = serialize_federation_envelope(envelope)
    request = httpx.Request(
        "POST",
        url,
        headers={
            "Content-Digest": content_digest(body),
            "Content-Type": "application/json",
            "Date": format_datetime(signing_time, usegmt=True),
        },
        content=body,
    )
    resolver = _StaticKeyResolver(
        key_id=signing_key.key_id,
        private_key=signing_key.private_key,
    )
    signer = HTTPMessageSigner(
        signature_algorithm=algorithms.ED25519,
        key_resolver=resolver,
    )
    signer.sign(
        request,
        key_id=signing_key.key_id,
        created=signing_time,
        label=FEDERATION_SIGNATURE_LABEL,
        covered_component_ids=FEDERATION_COVERED_COMPONENTS,
    )
    return SignedFederationRequest(
        method=request.method,
        url=str(request.url),
        headers=httpx.Headers(request.headers),
        body=body,
    )


def _headers(headers: HeaderInput) -> httpx.Headers:
    try:
        parsed = httpx.Headers(headers)
    except (TypeError, ValueError) as exc:
        raise FederationSignatureError("malformed HTTP headers") from exc
    for name in _SINGLETON_HEADERS:
        if len(parsed.get_list(name)) != 1:
            raise FederationSignatureError(f'exactly one "{name}" header is required')
    return parsed


def _top_level_member_count(value: str) -> int:
    """Count structured-field dictionary members without trusting overwrite parsing."""

    count = 1
    in_string = False
    in_bytes = False
    escaped = False
    inner_list_depth = 0
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if in_bytes:
            if character == ":":
                in_bytes = False
            continue
        if character == '"':
            in_string = True
        elif character == ":":
            in_bytes = True
        elif character == "(":
            inner_list_depth += 1
        elif character == ")":
            inner_list_depth -= 1
        elif character == "," and inner_list_depth == 0:
            count += 1
    return count


def _parameter_names(value: str) -> list[str]:
    """Return SFV parameter names, including duplicates hidden by dict parsing."""

    names: list[str] = []
    in_string = False
    in_bytes = False
    escaped = False
    index = 0
    while index < len(value):
        character = value[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if in_bytes:
            if character == ":":
                in_bytes = False
            index += 1
            continue
        if character == '"':
            in_string = True
            index += 1
            continue
        if character == ":":
            in_bytes = True
            index += 1
            continue
        if character != ";":
            index += 1
            continue

        index += 1
        start = index
        while index < len(value) and (value[index].isalnum() or value[index] in "_.*-"):
            index += 1
        if index > start:
            names.append(value[start:index].lower())
    return names


def _signature_input(headers: httpx.Headers) -> tuple[str, int]:
    raw_signature_input = headers["Signature-Input"]
    if _top_level_member_count(raw_signature_input) != 1:
        raise FederationSignatureError("exactly one signature input is required")
    try:
        node = http_sfv.Dictionary()
        node.parse(raw_signature_input.encode("ascii"))
    except Exception as exc:
        raise FederationSignatureError("malformed Signature-Input header") from exc
    if len(node) != 1:
        raise FederationSignatureError("exactly one signature input is required")

    signature_input = next(iter(node.values()))
    parameter_names = _parameter_names(raw_signature_input)
    if len(parameter_names) != len(set(parameter_names)):
        raise FederationSignatureError("duplicate signature parameters are not allowed")
    parameters = dict(signature_input.params)
    if set(parameters) != _REQUIRED_SIGNATURE_PARAMETERS:
        raise FederationSignatureError(
            "signature parameters must be exactly created, keyid, and alg"
        )
    key_id = parameters["keyid"]
    created = parameters["created"]
    if not isinstance(key_id, str) or not key_id:
        raise FederationSignatureError("signature keyid must be a non-empty string")
    if type(created) is not int:
        raise FederationSignatureError("signature created parameter must be an integer")
    if parameters["alg"] != "ed25519":
        raise FederationSignatureError("signature algorithm must be ed25519")
    return key_id, created


def _validate_signature_header(headers: httpx.Headers) -> None:
    raw_signature = headers["Signature"]
    if _top_level_member_count(raw_signature) != 1:
        raise FederationSignatureError("exactly one signature is required")
    try:
        node = http_sfv.Dictionary()
        node.parse(raw_signature.encode("ascii"))
    except Exception as exc:
        raise FederationSignatureError("malformed Signature header") from exc
    if len(node) != 1:
        raise FederationSignatureError("exactly one signature is required")
    signature = next(iter(node.values()))
    if not isinstance(signature.value, bytes) or signature.params:
        raise FederationSignatureError(
            "Signature must contain one unparameterized value"
        )


def signature_key_id(headers: HeaderInput) -> str:
    """Extract a strictly parsed key ID before discovery."""

    return _signature_input(_headers(headers))[0]


def _verify_digest(headers: httpx.Headers, body: bytes) -> None:
    match = _CONTENT_DIGEST_RE.fullmatch(headers["Content-Digest"])
    if match is None:
        raise FederationSignatureError(
            "Content-Digest must contain exactly one sha-256 digest"
        )
    try:
        supplied = base64.b64decode(match.group(1), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FederationSignatureError("Content-Digest is not valid base64") from exc
    expected = hashlib.sha256(body).digest()
    if len(supplied) != len(expected) or not hmac.compare_digest(supplied, expected):
        raise FederationSignatureError("Content-Digest does not match the body")


def _verify_date(
    headers: httpx.Headers,
    *,
    now: datetime,
    max_age: timedelta,
) -> None:
    try:
        value = parsedate_to_datetime(headers["Date"])
    except (TypeError, ValueError) as exc:
        raise FederationSignatureError("Date must be a valid HTTP date") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise FederationSignatureError("Date must include a timezone")
    if abs(now - value.astimezone(UTC)) > max_age + FEDERATION_CLOCK_SKEW:
        raise FederationSignatureError("Date is outside the allowed freshness window")


def _covered_component_names(covered: Mapping[str, str]) -> frozenset[str]:
    names: set[str] = set()
    for identifier in covered:
        if identifier == '"@signature-params"':
            continue
        if not (identifier.startswith('"') and identifier.endswith('"')):
            raise FederationSignatureError("unsupported signed component identifier")
        names.add(identifier[1:-1])
    return frozenset(names)


def verify_federation_request(
    *,
    method: str,
    url: str,
    headers: HeaderInput,
    body: bytes,
    key_id: str,
    public_key: Ed25519PublicKey,
    max_age: timedelta = FEDERATION_SIGNATURE_MAX_AGE,
    now: datetime | None = None,
) -> VerifiedFederationSignature:
    """Verify exact bytes and all mandatory MAIL signature components."""

    _validate_request_url(url)
    parsed_headers = _headers(headers)
    _validate_signature_header(parsed_headers)
    parsed_key_id, created_timestamp = _signature_input(parsed_headers)
    if not hmac.compare_digest(parsed_key_id, key_id):
        raise FederationSignatureError("signature key ID is not the expected key")
    if (
        parsed_headers["Content-Type"].split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise FederationSignatureError("Content-Type must be application/json")
    _verify_digest(parsed_headers, body)

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise FederationSignatureError("verification time must be timezone-aware")
    _verify_date(parsed_headers, now=current_time.astimezone(UTC), max_age=max_age)

    request = httpx.Request(method, url, headers=parsed_headers, content=body)
    resolver = _StaticKeyResolver(key_id=key_id, public_key=public_key)
    verifier = HTTPMessageVerifier(
        signature_algorithm=algorithms.ED25519,
        key_resolver=resolver,
    )
    try:
        results = verifier.verify(request, max_age=max_age)
    except (HTTPMessageSignaturesException, ValueError) as exc:
        raise FederationCryptographicSignatureError(
            "invalid federation request signature"
        ) from exc
    if len(results) != 1:
        raise FederationSignatureError("exactly one valid signature is required")

    covered_components = _covered_component_names(results[0].covered_components)
    missing = set(FEDERATION_COVERED_COMPONENTS) - covered_components
    if missing:
        raise FederationSignatureError(
            "signature does not cover every required request component"
        )
    return VerifiedFederationSignature(
        key_id=key_id,
        created=datetime.fromtimestamp(created_timestamp, tz=UTC),
        covered_components=covered_components,
    )


async def verify_federation_request_with_discovery(
    *,
    sender_host: str,
    method: str,
    url: str,
    headers: HeaderInput,
    body: bytes,
    discovery: _DiscoveryResolver,
    max_age: timedelta = FEDERATION_SIGNATURE_MAX_AGE,
) -> VerifiedFederationSignature:
    """Resolve an advertised key and retry once after a cached-key failure."""

    key_id = signature_key_id(headers)
    resolved = await discovery.resolve_public_key(sender_host, key_id)

    def verify(resolution: _ResolvedKey) -> VerifiedFederationSignature:
        public_key = public_key_from_manifest(resolution.key)
        return verify_federation_request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            key_id=key_id,
            public_key=public_key,
            max_age=max_age,
        )

    try:
        return verify(resolved)
    except FederationCryptographicSignatureError:
        if not resolved.manifest_from_cache:
            raise
    refreshed = await discovery.refresh_public_key(sender_host, key_id)
    return verify(refreshed)
