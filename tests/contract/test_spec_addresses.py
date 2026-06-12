# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
SPEC.md §6 (Addresses) conformance.

Each test cites the clause it enforces. The reference implementation
enforces the SHOULD-level 32-character identifier bound as a hard
limit; those tests cite both the spec clause and the implementation
constant.
"""

import pytest
from mail_protocol.core.constants import (
    AGENT_NAME_LEN_MAX,
    USER_NAME_LEN_MAX,
)
from mail_protocol.core.validators import validate_mail_address

# ─── §6.1 Host-scoped addresses: {ua_type}:{ua_id}@{host} ──────────


@pytest.mark.parametrize(
    "address",
    [
        "admin:root@localhost",
        "admin:root@example.com",
        "daemon:worker-1@example.com",
        "user:alice@localhost",
        "user:alice@10.0.0.1",
    ],
)
def test_valid_host_scoped_addresses_accepted(address: str) -> None:
    """§6.1: ua_type MUST be one of admin, daemon, user; ua_id MUST be
    a slug; host MUST be a domain name (or IP in the reference impl)."""

    assert validate_mail_address(address) == address


def test_unknown_ua_type_rejected() -> None:
    """§6.1: the ua_type prefix MUST be one of `admin`, `daemon`, `user`."""

    with pytest.raises(ValueError):
        validate_mail_address("bot:alice@localhost")


@pytest.mark.parametrize(
    "address",
    [
        "user:@localhost",  # ua_id MUST be at least 1 character
        "user:Alice@localhost",  # slugs are lowercase
        "user:has space@localhost",  # slugs have no whitespace
        "user:alice@not a host",  # host MUST be a valid domain name
    ],
)
def test_malformed_host_scoped_addresses_rejected(address: str) -> None:
    """§6.1: ua_id MUST be a slug string of at least 1 character."""

    with pytest.raises(ValueError):
        validate_mail_address(address)


def test_user_id_length_bound() -> None:
    """§6.1: ua_id MUST be >= 1 char and SHOULD be <= 32 chars. The
    reference implementation enforces USER_NAME_LEN_MAX as a hard cap."""

    longest = "a" * USER_NAME_LEN_MAX
    assert validate_mail_address(f"user:{longest}@localhost")
    with pytest.raises(ValueError):
        validate_mail_address(f"user:{longest}a@localhost")


# ─── §6.2 Swarm-scoped addresses: {address_id}@{swarm}@{host} ──────


@pytest.mark.parametrize(
    "address",
    [
        "sage@chorus@localhost",
        "supervisor@swarm-1@example.com",
        "list:all@chorus@localhost",
        "list:welfare-discourse@chorus@example.com",
    ],
)
def test_valid_swarm_scoped_addresses_accepted(address: str) -> None:
    """§6.2: address_id MUST be either {agent} or list:{list_id}."""

    assert validate_mail_address(address) == address


def test_unknown_swarm_scoped_prefix_rejected() -> None:
    """§6.2: the only prefixed swarm-scoped form is list:{list_id}."""

    with pytest.raises(ValueError):
        validate_mail_address("agent:sage@chorus@localhost")


@pytest.mark.parametrize(
    "address",
    [
        "Sage@chorus@localhost",  # agent MUST be a slug
        "sage@Chorus@localhost",  # swarm MUST be a slug
        "sage@chorus@not a host",  # host MUST be a valid domain name
        "list:@chorus@localhost",  # list_id MUST be at least 1 char
    ],
)
def test_malformed_swarm_scoped_addresses_rejected(address: str) -> None:
    """§6.2: agent, swarm, and list_id MUST be slug strings; host MUST
    be a valid domain name."""

    with pytest.raises(ValueError):
        validate_mail_address(address)


def test_agent_name_length_bound() -> None:
    """§6.2: agent MUST be >= 1 char and SHOULD be <= 32 chars. The
    reference implementation enforces AGENT_NAME_LEN_MAX as a hard cap."""

    longest = "a" * AGENT_NAME_LEN_MAX
    assert validate_mail_address(f"{longest}@chorus@localhost")
    with pytest.raises(ValueError):
        validate_mail_address(f"{longest}a@chorus@localhost")


# ─── §6: structural requirements ───────────────────────────────────


@pytest.mark.parametrize(
    "address",
    [
        "alice",
        "alice@localhost",  # bare two-part form without a ua_type prefix
        "a@b@c@d",
        "",
    ],
)
def test_invalid_address_structures_rejected(address: str) -> None:
    """§6: an address MUST be either host-scoped (§6.1) or swarm-scoped
    (§6.2); nothing else is a MAIL address."""

    with pytest.raises(ValueError):
        validate_mail_address(address)
