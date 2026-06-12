# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
Back-fill for the mail_protocol validators not covered by the contract
suite's SPEC.md §6/§7 tests (which exercise validate_mail_address and
the message-field validators).
"""

import pytest
from mail_protocol.core import validators as v

UUID = "55555555-5555-4555-8555-555555555555"


# ─── UUIDs ─────────────────────────────────────────────────────────


def test_validate_uuid_accepts_uuid() -> None:
    assert v.validate_uuid(UUID) == UUID


@pytest.mark.parametrize("value", ["", "not-a-uuid", "5555-5555"])
def test_validate_uuid_rejects_non_uuid(value: str) -> None:
    with pytest.raises(ValueError):
        v.validate_uuid(value)


def test_validate_uuids_checks_every_entry() -> None:
    assert v.validate_uuids([UUID, UUID]) == [UUID, UUID]
    with pytest.raises(ValueError):
        v.validate_uuids([UUID, "nope"])


# ─── slugs ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["a", "sage", "swarm-1", "a1-b2-c3"])
def test_string_is_slug_accepts(value: str) -> None:
    assert v.string_is_slug(value)


@pytest.mark.parametrize(
    "value", ["", "Sage", "has space", "-leading", "trailing-", "under_score", "a--b"]
)
def test_string_is_slug_rejects(value: str) -> None:
    assert not v.string_is_slug(value)


# ─── message recipients (SPEC.md §7.3) ─────────────────────────────


def test_validate_message_recipients_accepts_non_empty() -> None:
    addrs = ["sage@chorus@localhost", "user:alice@localhost"]
    assert v.validate_message_recipients(addrs) == addrs


def test_validate_message_recipients_rejects_empty_list() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        v.validate_message_recipients([])


def test_validate_mail_addresses_permits_empty_list() -> None:
    """Unlike message recipients, a generic address list (e.g. list
    members) may legitimately be empty."""

    assert v.validate_mail_addresses([]) == []


# ─── local addresses (agent@swarm) ─────────────────────────────────


def test_validate_local_address_accepts_agent_at_swarm() -> None:
    assert v.validate_local_address("sage@chorus") == "sage@chorus"


@pytest.mark.parametrize("value", ["sage", "sage@chorus@localhost", "Sage@chorus"])
def test_validate_local_address_rejects_other_forms(value: str) -> None:
    with pytest.raises(ValueError):
        v.validate_local_address(value)


def test_validate_local_addresses_checks_every_entry() -> None:
    with pytest.raises(ValueError):
        v.validate_local_addresses(["sage@chorus", "nope"])


# ─── swarm descriptions and keywords ───────────────────────────────


def test_validate_swarm_description_bounds() -> None:
    assert v.validate_swarm_description("A fine swarm.")
    assert v.validate_swarm_description("") == ""  # empty is allowed (min 0)
    with pytest.raises(ValueError):
        v.validate_swarm_description("d" * 256)  # max 255


def test_validate_swarm_keyword_must_be_slug() -> None:
    assert v.validate_swarm_keyword("testing") == "testing"
    with pytest.raises(ValueError):
        v.validate_swarm_keyword("Not A Slug")


def test_validate_swarm_keywords_checks_every_entry() -> None:
    assert v.validate_swarm_keywords(["a", "b"]) == ["a", "b"]
    with pytest.raises(ValueError):
        v.validate_swarm_keywords(["fine", ""])


# ─── webhook identifiers and events ────────────────────────────────


def test_validate_webhook_id_requires_wh_prefix_and_uuid() -> None:
    assert v.validate_webhook_id(f"wh_{UUID}")
    for bad in (UUID, f"hook_{UUID}", "wh_not-a-uuid", "wh_"):
        with pytest.raises(ValueError):
            v.validate_webhook_id(bad)


def test_validate_webhook_message_id_requires_msg_prefix_and_uuid() -> None:
    assert v.validate_webhook_message_id(f"msg_{UUID}")
    for bad in (UUID, f"wh_{UUID}", "msg_not-a-uuid"):
        with pytest.raises(ValueError):
            v.validate_webhook_message_id(bad)


def test_validate_webhook_event_type_allowlist() -> None:
    assert v.validate_webhook_event_type("mail.delivered") == "mail.delivered"
    with pytest.raises(ValueError):
        v.validate_webhook_event_type("mail.exploded")


def test_validate_webhook_event_types_checks_every_entry() -> None:
    with pytest.raises(ValueError):
        v.validate_webhook_event_types(["mail.delivered", "mail.exploded"])


# ─── hosts ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["localhost", "example.com", "10.0.0.1", "::1"])
def test_validate_host_accepts_hostnames_and_ips(value: str) -> None:
    assert v.validate_host(value) == value


@pytest.mark.parametrize("value", ["", "not a host", "exa mple.com"])
def test_validate_host_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        v.validate_host(value)
