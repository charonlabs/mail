# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs

"""SPEC.md §8.3 MAIL Federation v1 data-contract conformance."""

import base64
from datetime import UTC, datetime
from typing import Any

import pytest
from mail_protocol.core.federation import (
    MAILFederationManifest,
    MAILFederationPolicyHints,
    MAILFederationPublicKey,
    MAILInterServerMessage,
    mail_address_host,
)
from mail_protocol.core.messages import MAILMessage
from mail_protocol.network.federation import (
    FEDERATION_DELIVERY_PATH_V1,
    MAILFederationAcceptedResponse,
    MAILFederationErrorResponse,
)
from pydantic import ValidationError

ENVELOPE_ID = "77777777-7777-4777-8777-777777777777"
MESSAGE_ID = "55555555-5555-4555-8555-555555555555"


def make_message(**overrides: Any) -> MAILMessage:
    fields: dict[str, Any] = {
        "mail_version": "2.0",
        "message_id": MESSAGE_ID,
        "sender": "user:alice@server-a.example.com",
        "recipients": ["bob@village@server-b.example.com"],
        "subject": "Federated hello",
        "body": "Hello from server A.",
        "tags": ["federated"],
        "sent_at": datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
        "metadata": {"trace": "preserved"},
    }
    fields.update(overrides)
    return MAILMessage(**fields)


def make_envelope(**overrides: Any) -> MAILInterServerMessage:
    fields: dict[str, Any] = {
        "message_id": ENVELOPE_ID,
        "sender_host": "server-a.example.com",
        "recipient_host": "server-b.example.com",
        "message": make_message(),
        "metadata": {},
        "sent_at": datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
        "protocol_version": "1",
    }
    fields.update(overrides)
    return MAILInterServerMessage(**fields)


def make_public_key(key_id: str = "mail-federation-2026-09"):
    return MAILFederationPublicKey(
        key_id=key_id,
        algorithm="ed25519",
        public_key=base64.b64encode(bytes(range(32))).decode("ascii"),
    )


def test_canonical_reference_route_is_versioned() -> None:
    """§8.3.1: the reference implementation uses the v1 route."""

    assert FEDERATION_DELIVERY_PATH_V1 == "/daemon/deliver/remote/v1"


@pytest.mark.parametrize(
    ("address", "host"),
    [
        ("bob@village@server-b.example.com", "server-b.example.com"),
        ("list:all@village@server-b.example.com", "server-b.example.com"),
        ("user:bob@server-b.example.com", "server-b.example.com"),
        ("admin:root@server-b.example.com", "server-b.example.com"),
        ("daemon:worker@server-b.example.com", "server-b.example.com"),
    ],
)
def test_host_extraction_covers_every_address_shape(address: str, host: str) -> None:
    """§8.3.5: grouping uses the final host of every MAIL address shape."""

    assert mail_address_host(address) == host


def test_well_formed_manifest_is_accepted() -> None:
    """§8.3.1: required discovery fields form a strict manifest."""

    manifest = MAILFederationManifest(
        protocol_version="1",
        mail_protocol_version="2.0",
        delivery_url=(f"https://server-b.example.com{FEDERATION_DELIVERY_PATH_V1}"),
        public_keys=[make_public_key()],
        policy_hints=MAILFederationPolicyHints(accepts="allowlist"),
    )
    assert str(manifest.delivery_url) == (
        "https://server-b.example.com/daemon/deliver/remote/v1"
    )
    assert manifest.public_keys[0].algorithm == "ed25519"


@pytest.mark.parametrize(
    "url",
    [
        "http://server-b.example.com/daemon/deliver/remote/v1",
        "/daemon/deliver/remote/v1",
        "not a URL",
    ],
)
def test_manifest_delivery_url_must_be_absolute_https(url: str) -> None:
    """§8.3.1: production discovery never advertises plaintext delivery."""

    with pytest.raises(ValidationError):
        MAILFederationManifest(
            protocol_version="1",
            delivery_url=url,
            public_keys=[make_public_key()],
        )


def test_manifest_requires_at_least_one_unique_key_id() -> None:
    """§8.3.1: public_keys is non-empty and key IDs are unique."""

    with pytest.raises(ValidationError):
        MAILFederationManifest(
            protocol_version="1",
            delivery_url="https://server-b.example.com/remote/v1",
            public_keys=[],
        )
    with pytest.raises(ValidationError):
        MAILFederationManifest(
            protocol_version="1",
            delivery_url="https://server-b.example.com/remote/v1",
            public_keys=[make_public_key(), make_public_key()],
        )


@pytest.mark.parametrize(
    "public_key",
    ["not-base64!", base64.b64encode(b"too short").decode("ascii")],
)
def test_manifest_key_must_be_base64_ed25519_public_bytes(public_key: str) -> None:
    """§8.3.1: an Ed25519 public key is exactly 32 decoded bytes."""

    with pytest.raises(ValidationError):
        MAILFederationPublicKey(
            key_id="active-key", algorithm="ed25519", public_key=public_key
        )


def test_envelope_preserves_the_inner_message() -> None:
    """§8.3.2: transport wrapping does not mutate message metadata."""

    envelope = make_envelope()
    assert envelope.message.message_id == MESSAGE_ID
    assert envelope.message.metadata == {"trace": "preserved"}
    assert envelope.message.tags == ["federated"]


def test_envelope_id_is_distinct_from_inner_message_id() -> None:
    """§8.3.2: envelope and payload IDs have separate identities."""

    with pytest.raises(ValidationError):
        make_envelope(message_id=MESSAGE_ID)


def test_sender_host_must_match_inner_sender() -> None:
    """§8.3.2: the claimed origin is bound to the inner sender host."""

    with pytest.raises(ValidationError):
        make_envelope(sender_host="attacker.example.com")


def test_all_recipients_must_match_one_destination() -> None:
    """§8.3.2/§8.3.5: one envelope contains one host's recipients."""

    message = make_message(
        recipients=[
            "bob@village@server-b.example.com",
            "carol@village@server-c.example.com",
        ]
    )
    with pytest.raises(ValidationError):
        make_envelope(message=message)


def test_federated_list_recipient_is_rejected() -> None:
    """§8.3.2: mailing-list federation is outside v1."""

    message = make_message(recipients=["list:all@village@server-b.example.com"])
    with pytest.raises(ValidationError):
        make_envelope(message=message)


def test_envelope_requires_timezone_aware_sent_at() -> None:
    """§8.3.2: sent_at is an aware RFC 3339 timestamp."""

    with pytest.raises(ValidationError):
        make_envelope(sent_at=datetime(2026, 9, 14, 18, 0))


def test_envelope_protocol_version_is_one() -> None:
    """§8.3: federation and MAIL versions evolve independently."""

    assert make_envelope().protocol_version == "1"
    with pytest.raises(ValidationError):
        make_envelope(protocol_version="2")


def test_models_reject_unknown_fields() -> None:
    """The signed v1 structures have no ambiguous extension fields."""

    with pytest.raises(ValidationError):
        MAILInterServerMessage(
            **make_envelope().model_dump(), unexpected_transport_field=True
        )


def test_federation_response_models_capture_machine_readable_contract() -> None:
    """§8.3.4: clients use code, never human detail, for behavior."""

    accepted = MAILFederationAcceptedResponse(
        accepted_at=datetime(2026, 9, 14, 18, 0, tzinfo=UTC)
    )
    assert accepted.accepted_at is not None

    error = MAILFederationErrorResponse(
        code="policy_denied", detail="peer is not accepted"
    )
    assert error.failed_recipients is None

    # Unknown future codes remain parseable; status class supplies fallback.
    future = MAILFederationErrorResponse(code="future_policy", detail="rejected")
    assert future.code == "future_policy"


def test_recipient_not_found_error_requires_failed_recipients() -> None:
    """§8.3.4: unknown-recipient partitioning is machine-readable."""

    with pytest.raises(ValidationError):
        MAILFederationErrorResponse(
            code="recipient_not_found", detail="recipient not found"
        )

    response = MAILFederationErrorResponse(
        code="recipient_not_found",
        detail="one or more recipients were not found",
        failed_recipients=["ghost@village@server-b.example.com"],
    )
    assert response.failed_recipients == ["ghost@village@server-b.example.com"]
