# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from mail.core.message import (
    create_agent_address,
    create_system_address,
    create_user_address,
    format_agent_address,
    get_address_string,
    get_address_type,
    parse_agent_address,
)


def test_parse_and_format_agent_address():
    """
    Test that `parse_agent_address` and `format_agent_address` work as expected.
    """
    a, s = parse_agent_address("helper")
    assert a == "helper" and s is None

    a2, s2 = parse_agent_address("helper@swarm-x")
    assert a2 == "helper" and s2 == "swarm-x"

    fmt1 = format_agent_address("supervisor")
    assert fmt1["address"] == "supervisor"
    fmt2 = format_agent_address("supervisor", "example")
    assert fmt2["address"] == "supervisor@example"


def test_get_address_helpers():
    """
    Test that `get_address_string` and `get_address_type` work as expected.
    """
    addr = create_agent_address("analyst")
    assert get_address_string(addr) == "analyst"
    assert get_address_type(addr) == "agent"

    addr = create_user_address("user-1")
    assert get_address_string(addr) == "user-1"
    assert get_address_type(addr) == "user"

    addr = create_system_address("example-swarm")
    assert get_address_string(addr) == "example-swarm"
    assert get_address_type(addr) == "system"
