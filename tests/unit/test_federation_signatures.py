# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Unit tests for MAIL's RFC 9421 request-signature profile."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from http_message_signatures import (
    HTTPMessageSigner,
    HTTPSignatureKeyResolver,
    algorithms,
)
from mail_protocol.core.federation import MAILInterServerMessage
from mail_protocol.core.messages import MAILMessage
from mail_server.federation.keys import FederationPrivateKey
from mail_server.federation.signatures import (
    FEDERATION_COVERED_COMPONENTS,
    FederationSignatureError,
    content_digest,
    serialize_federation_envelope,
    sign_federation_request,
    verify_federation_request,
)

DELIVERY_URL = "https://server-b.example.com/daemon/deliver/remote/v1"


class PrivateResolver(HTTPSignatureKeyResolver):
    def __init__(self, key: Ed25519PrivateKey) -> None:
        self.key = key

    def resolve_private_key(self, _key_id: str) -> Ed25519PrivateKey:
        return self.key


def make_envelope(**overrides: Any) -> MAILInterServerMessage:
    now = datetime.now(UTC).replace(microsecond=0)
    message = MAILMessage(
        mail_version="2.0",
        message_id="55555555-5555-4555-8555-555555555555",
        sender="user:alice@server-a.example.com",
        recipients=["bob@village@server-b.example.com"],
        subject="Federated hello",
        body="Hello, federation!",
        tags=["federated"],
        sent_at=now,
        metadata={"unicode": "café"},
    )
    fields: dict[str, Any] = {
        "message_id": "77777777-7777-4777-8777-777777777777",
        "sender_host": "server-a.example.com",
        "recipient_host": "server-b.example.com",
        "message": message,
        "metadata": {},
        "sent_at": now,
        "protocol_version": "1",
    }
    fields.update(overrides)
    return MAILInterServerMessage(**fields)


@pytest.fixture
def signing_key() -> FederationPrivateKey:
    private_key = Ed25519PrivateKey.generate()
    return FederationPrivateKey(
        key_id="active-2026-09",
        private_key=private_key,
        public_key_base64="unused-by-signing",
    )


def verify_signed(
    signed: Any,
    signing_key: FederationPrivateKey,
    **overrides: Any,
) -> None:
    values = {
        "method": signed.method,
        "url": signed.url,
        "headers": signed.headers,
        "body": signed.body,
        "key_id": signing_key.key_id,
        "public_key": signing_key.private_key.public_key(),
    }
    values.update(overrides)
    verified = verify_federation_request(**values)
    assert verified.key_id == signing_key.key_id
    assert set(FEDERATION_COVERED_COMPONENTS) <= verified.covered_components


def test_sign_and_verify_exact_request(signing_key: FederationPrivateKey) -> None:
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=make_envelope(),
        signing_key=signing_key,
    )

    assert signed.body == serialize_federation_envelope(make_envelope())
    assert signed.headers["Content-Digest"] == content_digest(signed.body)
    assert signed.headers["Signature-Input"].startswith(
        'sig1=("@method" "@target-uri" "@authority"'
    )
    verify_signed(signed, signing_key)


@pytest.mark.parametrize(
    ("field", "mutated"),
    [
        ("method", "PUT"),
        ("url", "https://server-b.example.com/a-different-path"),
        ("url", "https://other.example.com/daemon/deliver/remote/v1"),
        ("body", b"{}"),
    ],
)
def test_verification_detects_request_mutation(
    signing_key: FederationPrivateKey,
    field: str,
    mutated: Any,
) -> None:
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=make_envelope(),
        signing_key=signing_key,
    )

    with pytest.raises(FederationSignatureError):
        verify_signed(signed, signing_key, **{field: mutated})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("Content-Digest", "sha-256=:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=:"),
        ("Content-Type", "application/problem+json"),
        ("Date", "Sun, 13 Sep 2026 12:00:00 GMT"),
    ],
)
def test_verification_detects_signed_header_mutation(
    signing_key: FederationPrivateKey,
    name: str,
    value: str,
) -> None:
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=make_envelope(),
        signing_key=signing_key,
    )
    headers = httpx.Headers(signed.headers)
    headers[name] = value

    with pytest.raises(FederationSignatureError):
        verify_signed(signed, signing_key, headers=headers)


def test_verification_rejects_duplicate_security_headers(
    signing_key: FederationPrivateKey,
) -> None:
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=make_envelope(),
        signing_key=signing_key,
    )
    headers = list(signed.headers.multi_items())
    headers.append(("Signature", signed.headers["Signature"]))

    with pytest.raises(FederationSignatureError, match="exactly one"):
        verify_signed(signed, signing_key, headers=headers)


def test_verification_rejects_unsupported_signature_parameters(
    signing_key: FederationPrivateKey,
) -> None:
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=make_envelope(),
        signing_key=signing_key,
    )
    headers = httpx.Headers(signed.headers)
    headers["Signature-Input"] += ';nonce="not-supported"'

    with pytest.raises(FederationSignatureError, match="parameters"):
        verify_signed(signed, signing_key, headers=headers)


def test_verification_rejects_duplicate_signature_parameter(
    signing_key: FederationPrivateKey,
) -> None:
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=make_envelope(),
        signing_key=signing_key,
    )
    headers = httpx.Headers(signed.headers)
    headers["Signature-Input"] = headers["Signature-Input"].replace(
        ';alg="ed25519"',
        ';alg="ed25519";alg="ed25519"',
    )

    with pytest.raises(FederationSignatureError, match="duplicate"):
        verify_signed(signed, signing_key, headers=headers)


def test_verification_rejects_duplicate_dictionary_signature(
    signing_key: FederationPrivateKey,
) -> None:
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=make_envelope(),
        signing_key=signing_key,
    )
    headers = httpx.Headers(signed.headers)
    headers["Signature"] += f", {headers['Signature']}"

    with pytest.raises(FederationSignatureError, match="exactly one signature"):
        verify_signed(signed, signing_key, headers=headers)


def test_verification_requires_every_profile_component(
    signing_key: FederationPrivateKey,
) -> None:
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=make_envelope(),
        signing_key=signing_key,
    )
    request = httpx.Request(
        signed.method,
        signed.url,
        headers={
            name: value
            for name, value in signed.headers.items()
            if name.lower() not in {"signature", "signature-input"}
        },
        content=signed.body,
    )
    signer = HTTPMessageSigner(
        signature_algorithm=algorithms.ED25519,
        key_resolver=PrivateResolver(signing_key.private_key),
    )
    signer.sign(
        request,
        key_id=signing_key.key_id,
        label="sig1",
        covered_component_ids=tuple(
            component
            for component in FEDERATION_COVERED_COMPONENTS
            if component != "@authority"
        ),
    )

    with pytest.raises(FederationSignatureError, match="does not cover"):
        verify_signed(signed, signing_key, headers=request.headers)


def test_verification_rejects_stale_signature(
    signing_key: FederationPrivateKey,
) -> None:
    signed = sign_federation_request(
        url=DELIVERY_URL,
        envelope=make_envelope(),
        signing_key=signing_key,
        created=datetime.now(UTC) - timedelta(minutes=6),
    )

    with pytest.raises(FederationSignatureError):
        verify_signed(signed, signing_key)


def test_signing_requires_https(signing_key: FederationPrivateKey) -> None:
    with pytest.raises(FederationSignatureError, match="HTTPS"):
        sign_federation_request(
            url="http://server-b.example.com/remote/v1",
            envelope=make_envelope(),
            signing_key=signing_key,
        )
