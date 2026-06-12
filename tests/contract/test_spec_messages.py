# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
SPEC.md §7 (Messages) conformance, enforced against MAILMessage — the
authoritative wire contract per §7.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from mail_protocol.core.constants import (
    MESSAGE_BODY_LEN_MAX,
    MESSAGE_SUBJECT_LEN_MAX,
)
from mail_protocol.core.messages import MAILMessage
from pydantic import ValidationError


def make_message(**overrides: Any) -> MAILMessage:
    fields: dict[str, Any] = {
        "message_id": "55555555-5555-4555-8555-555555555555",
        "sender": "user:alice@localhost",
        "recipients": ["sage@chorus@localhost"],
        "subject": "A subject",
        "body": "A body.",
        "sent_at": datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
        "metadata": {},
    }
    fields.update(overrides)
    return MAILMessage(**fields)


def test_well_formed_message_accepted() -> None:
    """§7: the authoritative data contract is MAILMessage."""

    message = make_message()
    assert message.message_id == "55555555-5555-4555-8555-555555555555"


# ─── §7.1 Message IDs ──────────────────────────────────────────────


def test_message_id_must_be_uuid() -> None:
    """§7.1: message_id MUST be a UUID (RFC 9562)."""

    with pytest.raises(ValidationError):
        make_message(message_id="not-a-uuid")


# ─── §7.2 Senders ──────────────────────────────────────────────────


def test_sender_must_be_valid_address() -> None:
    """§7.2: sender MUST be a valid MAIL address per §6."""

    with pytest.raises(ValidationError):
        make_message(sender="not an address")


# ─── §7.3 Recipients ───────────────────────────────────────────────


def test_each_recipient_must_be_valid_address() -> None:
    """§7.3: each recipients entry MUST be a valid MAIL address per §6."""

    with pytest.raises(ValidationError):
        make_message(recipients=["sage@chorus@localhost", "not an address"])


def test_recipients_must_not_be_empty() -> None:
    """§7.3: recipients MUST contain at least 1 entry."""

    with pytest.raises(ValidationError):
        make_message(recipients=[])


# ─── §7.4 Subjects ─────────────────────────────────────────────────


def test_subject_must_not_be_empty() -> None:
    """§7.4: subject MUST be at least 1 character long."""

    with pytest.raises(ValidationError):
        make_message(subject="")


def test_subject_length_bound() -> None:
    """§7.4: subject SHOULD be no longer than 256 characters. The
    reference implementation enforces MESSAGE_SUBJECT_LEN_MAX (256) as
    a hard cap."""

    assert make_message(subject="s" * MESSAGE_SUBJECT_LEN_MAX)
    with pytest.raises(ValidationError):
        make_message(subject="s" * (MESSAGE_SUBJECT_LEN_MAX + 1))


# ─── §7.5 Bodies ───────────────────────────────────────────────────


def test_body_must_not_be_empty() -> None:
    """§7.5: body MUST be at least 1 character long."""

    with pytest.raises(ValidationError):
        make_message(body="")


def test_body_length_bound() -> None:
    """§7.5: no maximum body length is mandated by the spec; the
    reference implementation documents and enforces a 65535-character
    limit."""

    assert make_message(body="b" * MESSAGE_BODY_LEN_MAX)
    with pytest.raises(ValidationError):
        make_message(body="b" * (MESSAGE_BODY_LEN_MAX + 1))


# ─── §7.6 Timestamps ───────────────────────────────────────────────


def test_sent_at_accepts_rfc3339_string() -> None:
    """§7.6: sent_at MUST be a UTC timestamp per RFC 3339."""

    message = make_message(sent_at="2026-06-12T09:00:00+00:00")
    assert message.sent_at == datetime(2026, 6, 12, 9, 0, tzinfo=UTC)


def test_sent_at_rejects_non_timestamp() -> None:
    """§7.6: sent_at MUST be a timestamp."""

    with pytest.raises(ValidationError):
        make_message(sent_at="yesterday-ish")


# ─── §7.7 Metadata ─────────────────────────────────────────────────


def test_metadata_field_is_required_but_may_be_empty() -> None:
    """§7.7: every message MUST contain a metadata field; it MAY be {}."""

    assert make_message(metadata={}).metadata == {}
    with pytest.raises(ValidationError):
        MAILMessage(
            message_id="55555555-5555-4555-8555-555555555555",
            sender="user:alice@localhost",
            recipients=["sage@chorus@localhost"],
            subject="A subject",
            body="A body.",
            sent_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
            # metadata intentionally omitted
        )
