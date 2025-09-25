# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
from typing import Any

from .types import (
    SwarmsJSONAction,
    SwarmsJSONAgent,
    SwarmsJSONFile,
    SwarmsJSONSwarm,
)


def load_swarms_json_from_file(path: str) -> SwarmsJSONFile:
    """
    Load a `swarms.json` file from a given path.
    """
    with open(path) as f:
        contents = json.load(f)
        if not isinstance(contents, list):
            raise ValueError(f"swarms.json file at {path} must contain a list of swarms, actually got {type(contents)}")
        return SwarmsJSONFile(swarms=contents)


def load_swarms_json_from_string(contents: str) -> SwarmsJSONFile:
    """
    Load a `swarms.json` string from a given string of contents.
    """
    contents = json.loads(contents)
    if not isinstance(contents, list):
        raise ValueError(f"swarms.json string must contain a list of swarms, actually got {type(contents)}")
    return SwarmsJSONFile(swarms=contents)


def build_swarms_from_swarms_json(contents: list[Any]) -> list[SwarmsJSONSwarm]:
    """
    Build a list of `SwarmsJSONSwarm` from a list of `SwarmsJSONFile` contents.
    """
    for swarm_candidate in contents:
        validate_swarm_from_swarms_json(swarm_candidate)

    return [build_swarm_from_swarms_json(swarm_candidate) for swarm_candidate in contents]


def validate_swarm_from_swarms_json(swarm_candidate: Any) -> None:
    """
    Ensure the candidate is a valid `SwarmsJSONSwarm`.
    """
    if not isinstance(swarm_candidate, dict):
        raise ValueError(f"swarm candidate must be a dict, actually got {type(swarm_candidate)}")

    REQUIRED_FIELDS: dict[str, type] = {
        "name": str,
        "version": str,
        "entrypoint": str,
        "agents": list[Any],
        "actions": list[Any],
    }
    
    OPTIONAL_FIELDS: dict[str, type] = {
        "enable_interswarm": bool,
    }
    
    for field, field_type in REQUIRED_FIELDS.items():
        if field not in swarm_candidate:
            raise ValueError(f"swarm candidate must contain a '{field}' field")
        if not isinstance(swarm_candidate[field], field_type):
            raise ValueError(f"swarm candidate field '{field}' must be a {field_type.__name__}, actually got {type(swarm_candidate[field])}")
    
    for field, field_type in OPTIONAL_FIELDS.items():
        if field not in swarm_candidate:
            continue
        if not isinstance(swarm_candidate[field], field_type):
            raise ValueError(f"swarm candidate field '{field}' must be a {field_type.__name__}, actually got {type(swarm_candidate[field])}")
    
    return


def build_swarm_from_swarms_json(swarm_candidate: Any) -> SwarmsJSONSwarm:
    """
    Build a `SwarmsJSONSwarm` from a candidate.
    """
    validate_swarm_from_swarms_json(swarm_candidate)
    return SwarmsJSONSwarm(
        name=swarm_candidate["name"],
        version=swarm_candidate["version"],
        entrypoint=swarm_candidate["entrypoint"],
        agents=[build_agent_from_swarms_json(agent) for agent in swarm_candidate["agents"]],
        actions=[build_action_from_swarms_json(action) for action in swarm_candidate["actions"]],
        enable_interswarm=swarm_candidate.get("enable_interswarm", False),
    )


def validate_agent_from_swarms_json(agent_candidate: Any) -> None:
    """
    Ensure the candidate is a valid `SwarmsJSONAgent`.
    """
    if not isinstance(agent_candidate, dict):
        raise ValueError(f"agent candidate must be a dict, actually got {type(agent_candidate)}")
    
    REQUIRED_FIELDS: dict[str, type] = {
        "name": str,
        "factory": str,
        "comm_targets": list[str],
        "agent_params": dict[str, Any],
    }
    
    OPTIONAL_FIELDS: dict[str, type] = {
        "enable_entrypoint": bool,
        "enable_interswarm": bool,
        "can_complete_tasks": bool,
        "tool_format": str,
        "actions": list[str],
    }
    
    for field, field_type in REQUIRED_FIELDS.items():
        if field not in agent_candidate:
            raise ValueError(f"agent candidate must contain a '{field}' field")
        if not isinstance(agent_candidate[field], field_type):
            raise ValueError(f"agent candidate field '{field}' must be a {field_type.__name__}, actually got {type(agent_candidate[field])}")
    
    for field, field_type in OPTIONAL_FIELDS.items():
        if field not in agent_candidate:
            continue
        if not isinstance(agent_candidate[field], field_type):
            raise ValueError(f"agent candidate field '{field}' must be a {field_type.__name__}, actually got {type(agent_candidate[field])}")
    
    return


def build_agent_from_swarms_json(agent_candidate: Any) -> SwarmsJSONAgent:
    """
    Build a `SwarmsJSONAgent` from a candidate.
    """
    validate_agent_from_swarms_json(agent_candidate)
    return SwarmsJSONAgent(
        name=agent_candidate["name"],
        factory=agent_candidate["factory"],
        comm_targets=agent_candidate["comm_targets"],
        agent_params=agent_candidate["agent_params"],
        enable_entrypoint=agent_candidate.get("enable_entrypoint", False),
        enable_interswarm=agent_candidate.get("enable_interswarm", False),
        can_complete_tasks=agent_candidate.get("can_complete_tasks", False),
        tool_format=agent_candidate.get("tool_format", "responses"),
        actions=agent_candidate.get("actions", []),
    )


def validate_action_from_swarms_json(action_candidate: Any) -> None:
    """
    Ensure the candidate is a valid `SwarmsJSONAction`.
    """
    if not isinstance(action_candidate, dict):
        raise ValueError(f"action candidate must be a dict, actually got {type(action_candidate)}")
    
    REQUIRED_FIELDS: dict[str, type] = {
        "name": str,
        "description": str,
        "parameters": dict[str, Any],
        "function": str,
    }
    
    OPTIONAL_FIELDS: dict[str, type] = {
        "actions": list[str],
    }
    
    for field, field_type in REQUIRED_FIELDS.items():
        if field not in action_candidate:
            raise ValueError(f"action candidate must contain a '{field}' field")
        if not isinstance(action_candidate[field], field_type):
            raise ValueError(f"action candidate field '{field}' must be a {field_type.__name__}, actually got {type(action_candidate[field])}")
    
    for field, field_type in OPTIONAL_FIELDS.items():
        if field not in action_candidate:
            continue
        if not isinstance(action_candidate[field], field_type):
            raise ValueError(f"action candidate field '{field}' must be a {field_type.__name__}, actually got {type(action_candidate[field])}")
    
    return


def build_action_from_swarms_json(action_candidate: Any) -> SwarmsJSONAction:
    """
    Build a `SwarmsJSONAction` from a candidate.
    """
    validate_action_from_swarms_json(action_candidate)
    return SwarmsJSONAction(
        name=action_candidate["name"],
        description=action_candidate["description"],
        parameters=action_candidate["parameters"],
        function=action_candidate["function"],
    )