# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from datetime import UTC, datetime

import pytest
from mail_protocol.core.constants import (
    LIST_ADDRESS_PREFIX,
    LIST_NAME_LEN_MAX,
)
from mail_protocol.core.lists import (
    MAILList,
    MAILListInBackend,
    MAILListPolicy,
)
from mail_protocol.core.validators import (
    validate_list_name,
    validate_list_names,
    validate_mail_address,
)
from pydantic import ValidationError


def _make_list(
    *,
    name: str = "welfare-discourse",
    swarm: str = "chorus",
    host: str = "localhost",
    owner: str = "admin:ryan@localhost",
    members: list[str] | None = None,
) -> MAILList:
    return MAILList(
        name=name,
        swarm=swarm,
        host=host,
        owner=owner,
        members=members or [],
    )


# ─── List name validator ─────────────────────────────────────────────


def test_validate_list_name_accepts_lowercase_slug() -> None:
    assert validate_list_name("welfare-discourse") == "welfare-discourse"


def test_validate_list_name_rejects_uppercase() -> None:
    with pytest.raises(ValueError, match="invalid slug"):
        validate_list_name("WelfareDiscourse")


def test_validate_list_name_rejects_empty() -> None:
    with pytest.raises(ValueError, match="at least"):
        validate_list_name("")


def test_validate_list_name_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="no longer than"):
        validate_list_name("a" * (LIST_NAME_LEN_MAX + 1))


def test_validate_list_names_accepts_all_slugs() -> None:
    names = ["welfare-discourse", "alignment", "mail-v2"]
    assert validate_list_names(names) == names


def test_validate_list_names_rejects_any_invalid() -> None:
    with pytest.raises(ValueError):
        validate_list_names(["ok-name", "Bad_Name"])


# ─── MAIL address parser learns about lists ──────────────────────────


def test_validate_mail_address_accepts_list_form() -> None:
    addr = "list:welfare-discourse@chorus@localhost"
    assert validate_mail_address(addr) == addr


def test_validate_mail_address_rejects_unknown_prefix_in_three_parts() -> None:
    with pytest.raises(ValueError, match="invalid MAIL address structure"):
        validate_mail_address("group:welfare-discourse@chorus@localhost")


def test_validate_mail_address_still_accepts_plain_agent_form() -> None:
    addr = "philosopher@chorus@localhost"
    assert validate_mail_address(addr) == addr


def test_validate_mail_address_rejects_list_with_invalid_slug() -> None:
    with pytest.raises(ValueError, match="invalid slug"):
        validate_mail_address("list:Welfare_Discourse@chorus@localhost")


def test_validate_mail_address_rejects_list_with_invalid_swarm() -> None:
    with pytest.raises(ValueError, match="invalid slug"):
        validate_mail_address(
            "list:welfare-discourse@Bad_Swarm@localhost"
        )


def test_list_address_prefix_constant_matches_parser() -> None:
    addr = f"{LIST_ADDRESS_PREFIX}:welfare-discourse@chorus@localhost"
    assert validate_mail_address(addr) == addr


# ─── MAILList model ──────────────────────────────────────────────────


def test_mail_list_get_address_round_trips_validation() -> None:
    mail_list = _make_list()
    address = mail_list.get_address()
    assert address == "list:welfare-discourse@chorus@localhost"
    assert validate_mail_address(address) == address


def test_mail_list_defaults_to_empty_members_and_open_policy() -> None:
    mail_list = _make_list()
    assert mail_list.members == []
    assert mail_list.policy.visibility == "public"
    assert mail_list.policy.join_policy == "open"
    assert mail_list.policy.send_policy == "open"
    assert mail_list.metadata == {}


def test_mail_list_carries_member_addresses() -> None:
    mail_list = _make_list(
        members=[
            "philosopher@chorus@localhost",
            "minichorus-pm@minichorus@localhost",
            "user:ryan@localhost",
        ]
    )
    assert len(mail_list.members) == 3


def test_mail_list_rejects_invalid_member_address() -> None:
    with pytest.raises(ValidationError):
        _make_list(members=["definitely-not-a-mail-address"])


def test_mail_list_rejects_invalid_owner_address() -> None:
    with pytest.raises(ValidationError):
        _make_list(owner="ryan-without-host-or-prefix")


def test_mail_list_rejects_invalid_name() -> None:
    with pytest.raises(ValidationError):
        _make_list(name="Bad_Name")


def test_mail_list_rejects_invalid_swarm() -> None:
    with pytest.raises(ValidationError):
        _make_list(swarm="Bad_Swarm")


def test_mail_list_rejects_invalid_host() -> None:
    with pytest.raises(ValidationError):
        _make_list(host="not a host with spaces")


def test_mail_list_type_discriminator_is_list() -> None:
    mail_list = _make_list()
    assert mail_list.list_type == "list"


# ─── MAILListPolicy ──────────────────────────────────────────────────


def test_mail_list_policy_defaults_are_open_and_public() -> None:
    policy = MAILListPolicy()
    assert policy.visibility == "public"
    assert policy.join_policy == "open"
    assert policy.send_policy == "open"


def test_mail_list_policy_reserved_variants_validate() -> None:
    # The protocol layer permits the future-looking variants even
    # though the server endpoints reject them in v1.
    policy = MAILListPolicy(
        visibility="private",
        join_policy="approval",
        send_policy="admin-only",
    )
    assert policy.visibility == "private"
    assert policy.join_policy == "approval"
    assert policy.send_policy == "admin-only"


def test_mail_list_policy_rejects_unknown_variant() -> None:
    with pytest.raises(ValidationError):
        MAILListPolicy(visibility="ghosted")  # type: ignore[arg-type]


# ─── MAILListInBackend ───────────────────────────────────────────────


def test_mail_list_in_backend_requires_id_and_timestamps() -> None:
    now = datetime.now(UTC)
    record = MAILListInBackend(
        name="welfare-discourse",
        swarm="chorus",
        host="localhost",
        owner="admin:ryan@localhost",
        list_id="11111111-1111-1111-1111-111111111111",
        created_at=now,
        updated_at=now,
    )
    assert record.list_id == "11111111-1111-1111-1111-111111111111"
    assert record.created_at == now
    assert record.updated_at == now


def test_mail_list_in_backend_rejects_non_uuid_id() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        MAILListInBackend(
            name="welfare-discourse",
            swarm="chorus",
            host="localhost",
            owner="admin:ryan@localhost",
            list_id="not-a-uuid",
            created_at=now,
            updated_at=now,
        )


def test_mail_list_in_backend_inherits_address_method() -> None:
    now = datetime.now(UTC)
    record = MAILListInBackend(
        name="welfare-discourse",
        swarm="chorus",
        host="localhost",
        owner="admin:ryan@localhost",
        list_id="11111111-1111-1111-1111-111111111111",
        created_at=now,
        updated_at=now,
    )
    assert record.get_address() == "list:welfare-discourse@chorus@localhost"
