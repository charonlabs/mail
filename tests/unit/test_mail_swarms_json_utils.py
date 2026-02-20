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


def _minimal_agent(
    name: str,
    targets: list[str],
    enable_entrypoint: bool = False,
    can_complete_tasks: bool = False,
) -> dict[str, object]:
    return {
        "name": name,
        "factory": "tests.conftest:make_stub_agent",
        "comm_targets": targets,
        "agent_params": {},
        "enable_entrypoint": enable_entrypoint,
        "can_complete_tasks": can_complete_tasks,
    }


def test_load_swarms_json_from_string_accepts_valid_list() -> None:
    """
    Test that `load_swarms_json_from_string` accepts a valid list of swarms.
    """
    swarms = [
        {
            "name": "demo",
            "version": "1.3.5",
            "entrypoint": "alpha",
            "agents": [
                _minimal_agent(
                    "alpha", ["beta"], enable_entrypoint=True, can_complete_tasks=True
                ),
                _minimal_agent("beta", ["alpha"]),
            ],
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
        "version": "1.3.5",
        "entrypoint": "alpha",
        "agents": [
            _minimal_agent(
                "alpha", ["beta"], enable_entrypoint=True, can_complete_tasks=True
            ),
            _minimal_agent("beta", ["alpha"]),
        ],
        "actions": [_minimal_action()],
    }
    swarm = build_swarm_from_swarms_json(data)
    assert swarm["enable_interswarm"] is False
    assert swarm["action_imports"] == []
    beta = swarm["agents"][1]
    assert beta["enable_interswarm"] is False
    assert beta["actions"] == []
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
        "version": "1.3.5",
        "entrypoint": "alpha",
        "agents": [
            _minimal_agent("alpha", [], enable_entrypoint=True, can_complete_tasks=True)
        ],
        "actions": [],
        "action_imports": ["python::tests.conftest:make_stub_agent", 123],
    }
    with pytest.raises(ValueError) as exc:
        build_swarm_from_swarms_json(data)
    assert "action_imports" in str(exc.value)


# ── Cross-validation tests ──────────────────────────────────────────────────


def _valid_swarm(**overrides: object) -> dict[str, object]:
    """Build a minimal swarm dict that passes all cross-validation checks."""
    base: dict[str, object] = {
        "name": "demo",
        "version": "1.0.0",
        "entrypoint": "supervisor",
        "agents": [
            _minimal_agent(
                "supervisor",
                ["worker"],
                enable_entrypoint=True,
                can_complete_tasks=True,
            ),
            _minimal_agent("worker", ["supervisor"]),
        ],
        "actions": [],
    }
    base.update(overrides)
    return base


def test_cross_validate_entrypoint_not_in_agents() -> None:
    """Entrypoint name that doesn't match any agent raises ValueError."""
    data = _valid_swarm(entrypoint="nonexistent")
    with pytest.raises(
        ValueError, match="entrypoint 'nonexistent' does not match any agent name"
    ):
        build_swarm_from_swarms_json(data)


def test_cross_validate_entrypoint_not_in_agents_suggests_correction() -> None:
    """Error message includes 'Did you mean' when a close match exists."""
    data = _valid_swarm(entrypoint="supervisr")
    with pytest.raises(ValueError, match="Did you mean 'supervisor'"):
        build_swarm_from_swarms_json(data)


def test_cross_validate_no_entrypoint_agent() -> None:
    """No agent with enable_entrypoint: true raises ValueError."""
    data = _valid_swarm(
        agents=[
            _minimal_agent(
                "supervisor",
                ["worker"],
                enable_entrypoint=False,
                can_complete_tasks=True,
            ),
            _minimal_agent("worker", ["supervisor"]),
        ]
    )
    with pytest.raises(
        ValueError, match="no agent has 'enable_entrypoint' set to true"
    ):
        build_swarm_from_swarms_json(data)


def test_cross_validate_entrypoint_agent_missing_flag() -> None:
    """Entrypoint agent exists but lacks enable_entrypoint: true."""
    data = _valid_swarm(
        agents=[
            _minimal_agent(
                "supervisor",
                ["worker"],
                enable_entrypoint=False,
                can_complete_tasks=True,
            ),
            _minimal_agent("worker", ["supervisor"], enable_entrypoint=True),
        ]
    )
    with pytest.raises(ValueError, match="entrypoint agent 'supervisor' does not have"):
        build_swarm_from_swarms_json(data)


def test_cross_validate_comm_target_not_in_agents() -> None:
    """Bad comm_target raises ValueError with suggestion."""
    data = _valid_swarm(
        agents=[
            _minimal_agent(
                "supervisor", ["worke"], enable_entrypoint=True, can_complete_tasks=True
            ),
            _minimal_agent("worker", ["supervisor"]),
        ]
    )
    with pytest.raises(ValueError, match="Did you mean 'worker'"):
        build_swarm_from_swarms_json(data)


def test_cross_validate_comm_target_interswarm_allowed() -> None:
    """agent@swarm format comm_targets pass validation."""
    data = _valid_swarm(
        agents=[
            _minimal_agent(
                "supervisor",
                ["worker", "remote@other-swarm"],
                enable_entrypoint=True,
                can_complete_tasks=True,
            ),
            _minimal_agent("worker", ["supervisor"]),
        ]
    )
    # Should not raise
    build_swarm_from_swarms_json(data)


def test_cross_validate_no_supervisor() -> None:
    """No can_complete_tasks: true agent raises ValueError."""
    data = _valid_swarm(
        agents=[
            _minimal_agent(
                "supervisor",
                ["worker"],
                enable_entrypoint=True,
                can_complete_tasks=False,
            ),
            _minimal_agent("worker", ["supervisor"]),
        ]
    )
    with pytest.raises(
        ValueError, match="no agent has 'can_complete_tasks' set to true"
    ):
        build_swarm_from_swarms_json(data)


def test_cross_validate_duplicate_agent_names() -> None:
    """Two agents with the same name raises ValueError."""
    data = _valid_swarm(
        agents=[
            _minimal_agent(
                "supervisor",
                ["supervisor"],
                enable_entrypoint=True,
                can_complete_tasks=True,
            ),
            _minimal_agent("supervisor", ["supervisor"]),
        ]
    )
    with pytest.raises(ValueError, match="duplicate agent name 'supervisor'"):
        build_swarm_from_swarms_json(data)


def test_cross_validate_agent_action_not_in_swarm() -> None:
    """Agent references undefined action, raises ValueError with suggestion."""
    agent = _minimal_agent(
        "supervisor", ["worker"], enable_entrypoint=True, can_complete_tasks=True
    )
    agent["actions"] = ["pign"]
    data = _valid_swarm(
        agents=[agent, _minimal_agent("worker", ["supervisor"])],
        actions=[_minimal_action()],  # defines "ping"
    )
    with pytest.raises(ValueError, match="Did you mean 'ping'"):
        build_swarm_from_swarms_json(data)


def test_cross_validate_agent_action_with_imports_skips() -> None:
    """When action_imports present, unmatched agent action names don't error."""
    agent = _minimal_agent(
        "supervisor", ["worker"], enable_entrypoint=True, can_complete_tasks=True
    )
    agent["actions"] = ["imported_action"]
    data = _valid_swarm(
        agents=[agent, _minimal_agent("worker", ["supervisor"])],
        action_imports=["python::tests.conftest:make_stub_agent"],
    )
    # Should not raise (unmatched action may come from imports)
    build_swarm_from_swarms_json(data)


def test_cross_validate_valid_swarm_passes() -> None:
    """A well-formed swarm passes all cross-validation."""
    data = _valid_swarm()
    # Should not raise
    swarm = build_swarm_from_swarms_json(data)
    assert swarm["name"] == "demo"
