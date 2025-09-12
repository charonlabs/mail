from mail.core.message import (
    create_agent_address,
    format_agent_address,
    get_address_string,
    get_address_type,
    parse_agent_address,
)


def test_parse_and_format_agent_address():
    a, s = parse_agent_address("helper")
    assert a == "helper" and s is None

    a2, s2 = parse_agent_address("helper@swarm-x")
    assert a2 == "helper" and s2 == "swarm-x"

    fmt1 = format_agent_address("supervisor")
    assert fmt1["address"] == "supervisor"
    fmt2 = format_agent_address("supervisor", "example")
    assert fmt2["address"] == "supervisor@example"


def test_get_address_helpers():
    addr = create_agent_address("analyst")
    assert get_address_string(addr) == "analyst"
    assert get_address_type(addr) == "agent"

    # Backward-compat with plain strings
    assert get_address_string("user-1") == "user-1"
    assert get_address_type("user-1") == "agent"
