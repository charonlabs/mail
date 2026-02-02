# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json

import pytest

from mail.swarms_json.utils import (
    build_action_from_swarms_json,
    build_agent_from_swarms_json,
    build_swarm_from_swarms_json,
    build_swarms_from_swarms_json,
    load_swarms_json_from_string,
)


def _minimal_action() -> dict[str, object]:
    return {
        "name": "ping",
        "description": "Send a ping",
        "parameters": {"type": "object", "properties": {}},
        "function": "tests.conftest:make_stub_agent",
    }


def _minimal_agent(name: str, targets: list[str]) -> dict[str, object]:
    return {
        "name": name,
        "factory": "tests.conftest:make_stub_agent",
        "comm_targets": targets,
        "agent_params": {},
    }


def test_load_swarms_json_from_string_accepts_valid_list() -> None:
    """
    Test that `load_swarms_json_from_string` accepts a valid list of swarms.
    """
    swarms = [
        {
            "name": "demo",
            "version": "1.3.2",
            "entrypoint": "alpha",
            "agents": [],
            "actions": [],
        },
    ]
    loaded = load_swarms_json_from_string(json.dumps(swarms))
    assert loaded["swarms"] == swarms


def test_build_swarm_from_swarms_json_populates_defaults() -> None:
    """
    Test that `build_swarm_from_swarms_json` populates defaults.
    """
    data = {
        "name": "demo",
        "version": "1.3.2",
        "entrypoint": "alpha",
        "agents": [
            _minimal_agent("alpha", ["beta"]),
            _minimal_agent("beta", []),
        ],
        "actions": [_minimal_action()],
    }
    swarm = build_swarm_from_swarms_json(data)
    assert swarm["enable_interswarm"] is False
    assert swarm["action_imports"] == []
    alpha = swarm["agents"][0]
    assert alpha["enable_entrypoint"] is False
    assert alpha["enable_interswarm"] is False
    assert alpha["actions"] == []
    action = swarm["actions"][0]
    assert action["parameters"]["type"] == "object"


def test_build_agent_from_swarms_json_missing_required_field() -> None:
    """
    Test that `build_agent_from_swarms_json` raises an error if a required field is missing.
    """
    agent = _minimal_agent("alpha", [])
    agent.pop("agent_params")
    with pytest.raises(ValueError) as exc:
        build_agent_from_swarms_json(agent)
    assert "must contain" in str(exc.value)


def test_build_action_from_swarms_json_type_validation() -> None:
    """
    Test that `build_action_from_swarms_json` raises an error if a field is not the correct type.
    """
    action = _minimal_action()
    action["function"] = 123  # type: ignore[assignment]
    with pytest.raises(ValueError) as exc:
        build_action_from_swarms_json(action)
    assert "must be a" in str(exc.value)


def test_build_swarms_from_swarms_json_validates_each_entry() -> None:
    """
    Test that `build_swarms_from_swarms_json` raises an error if an entry is invalid.
    """
    invalid = {
        "name": "demo",
        "entrypoint": "alpha",
        "agents": [],
        "actions": [],
    }
    with pytest.raises(ValueError) as exc:
        build_swarms_from_swarms_json([invalid])
    assert "must contain" in str(exc.value)


def test_build_swarm_from_swarms_json_rejects_bad_action_imports() -> None:
    """
    `action_imports` must be a list of strings.
    """
    data = {
        "name": "demo",
        "version": "1.3.2",
        "entrypoint": "alpha",
        "agents": [_minimal_agent("alpha", [])],
        "actions": [],
        "action_imports": ["python::tests.conftest:make_stub_agent", 123],
    }
    with pytest.raises(ValueError) as exc:
        build_swarm_from_swarms_json(data)
    assert "action_imports" in str(exc.value)
