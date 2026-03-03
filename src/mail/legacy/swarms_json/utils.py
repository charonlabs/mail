# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import difflib
import json
import warnings
from typing import Any

from mail.utils.parsing import target_address_is_interswarm

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
            raise ValueError(
                f"swarms.json file at {path} must contain a list of swarms, actually got {type(contents)}"
            )
        for swarm in contents:
            validate_swarm_from_swarms_json(swarm)
        return SwarmsJSONFile(swarms=contents)


def load_swarms_json_from_string(contents: str) -> SwarmsJSONFile:
    """
    Load a `swarms.json` string from a given string of contents.
    """
    contents = json.loads(contents)
    if not isinstance(contents, list):
        raise ValueError(
            f"swarms.json string must contain a list of swarms, actually got {type(contents)}"
        )
    for swarm in contents:
        validate_swarm_from_swarms_json(swarm)
    return SwarmsJSONFile(swarms=contents)


def build_swarms_from_swarms_json(contents: list[Any]) -> list[SwarmsJSONSwarm]:
    """
    Build a list of `SwarmsJSONSwarm` from a list of `SwarmsJSONFile` contents.
    """
    for swarm_candidate in contents:
        validate_swarm_from_swarms_json(swarm_candidate)

    return [
        build_swarm_from_swarms_json(swarm_candidate) for swarm_candidate in contents
    ]


def validate_swarm_from_swarms_json(swarm_candidate: Any) -> None:
    """
    Ensure the candidate is a valid `SwarmsJSONSwarm`.
    """
    if not isinstance(swarm_candidate, dict):
        raise ValueError(
            f"swarm candidate must be a dict, actually got {type(swarm_candidate)}"
        )

    REQUIRED_FIELDS: dict[str, type] = {
        "name": str,
        "version": str,
        "entrypoint": str,
        "agents": list,
        "actions": list,
    }

    OPTIONAL_FIELDS: dict[str, type] = {
        "enable_interswarm": bool,
        "breakpoint_tools": list,
        "exclude_tools": list,
        "action_imports": list,
    }

    for field, field_type in REQUIRED_FIELDS.items():
        if field not in swarm_candidate:
            raise ValueError(f"swarm candidate must contain a '{field}' field")
        if not isinstance(swarm_candidate[field], field_type):
            raise ValueError(
                f"swarm candidate field '{field}' must be a {field_type.__name__}, actually got {type(swarm_candidate[field])}"
            )

    for field, field_type in OPTIONAL_FIELDS.items():
        if field not in swarm_candidate:
            continue
        if not isinstance(swarm_candidate[field], field_type):
            raise ValueError(
                f"swarm candidate field '{field}' must be a {field_type.__name__}, actually got {type(swarm_candidate[field])}"
            )

    if "action_imports" in swarm_candidate:
        imports = swarm_candidate["action_imports"]
        if any(not isinstance(item, str) for item in imports):
            raise ValueError(
                "swarm candidate field 'action_imports' must be a list of strings"
            )

    _cross_validate_swarm(swarm_candidate)

    return


def _suggest(word: str, possibilities: list[str]) -> str:
    """
    Return a " Did you mean '...'?" suffix if a close match exists, else empty string.
    """
    matches = difflib.get_close_matches(word, possibilities, n=1, cutoff=0.6)
    if matches:
        return f" Did you mean '{matches[0]}'?"
    return ""


def _cross_validate_swarm(swarm_candidate: dict[str, Any]) -> None:
    """
    Cross-validate structural relationships in a swarm dict.
    Called after all field-level checks pass.
    """
    agents = swarm_candidate.get("agents", [])
    actions = swarm_candidate.get("actions", [])
    entrypoint = swarm_candidate.get("entrypoint", "")
    action_imports = swarm_candidate.get("action_imports", [])

    # Collect agent names (defensively - agents may not all be dicts yet)
    agent_names: list[str] = []
    for agent in agents:
        if isinstance(agent, dict):
            name = agent.get("name")
            if isinstance(name, str):
                agent_names.append(name)

    # Check 7: duplicate agent names (check early so other checks are meaningful)
    seen_names: set[str] = set()
    for name in agent_names:
        if name in seen_names:
            raise ValueError(f"duplicate agent name '{name}'")
        seen_names.add(name)

    # Check 1: entrypoint matches an agent name
    if entrypoint not in agent_names:
        raise ValueError(
            f"entrypoint '{entrypoint}' does not match any agent name."
            + _suggest(entrypoint, agent_names)
        )

    # Check 2: at least one agent has enable_entrypoint: true
    has_entrypoint_flag = any(
        isinstance(a, dict) and a.get("enable_entrypoint") is True for a in agents
    )
    if not has_entrypoint_flag:
        raise ValueError(
            "no agent has 'enable_entrypoint' set to true; "
            "the swarm will reject all incoming messages"
        )

    # Check 3: the entrypoint agent specifically has enable_entrypoint: true
    for agent in agents:
        if isinstance(agent, dict) and agent.get("name") == entrypoint:
            if agent.get("enable_entrypoint") is not True:
                raise ValueError(
                    f"entrypoint agent '{entrypoint}' does not have "
                    "'enable_entrypoint' set to true"
                )
            break

    # Check 4: comm_targets reference valid agents or interswarm addresses
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_name = agent.get("name", "?")
        for target in agent.get("comm_targets", []):
            if not isinstance(target, str):
                continue
            if target_address_is_interswarm(target):
                continue
            if target not in agent_names:
                raise ValueError(
                    f"agent '{agent_name}' has comm_target '{target}' "
                    "which is not a defined agent." + _suggest(target, agent_names)
                )

    # Check 5: at least one agent has can_complete_tasks: true
    has_supervisor = any(
        isinstance(a, dict) and a.get("can_complete_tasks") is True for a in agents
    )
    if not has_supervisor:
        raise ValueError(
            "no agent has 'can_complete_tasks' set to true; "
            "no agent will be able to complete tasks"
        )

    # Check 6: agent action references exist in swarm actions
    action_names: list[str] = []
    for act in actions:
        if isinstance(act, dict):
            act_name = act.get("name")
            if isinstance(act_name, str):
                action_names.append(act_name)

    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_name = agent.get("name", "?")
        for action_ref in agent.get("actions", []):
            if not isinstance(action_ref, str):
                continue
            if action_ref in action_names:
                continue
            # When action_imports is non-empty, unmatched names may come from imports
            if action_imports:
                continue
            raise ValueError(
                f"agent '{agent_name}' references action '{action_ref}' "
                "which is not defined in the swarm's actions."
                + _suggest(action_ref, action_names)
            )


def build_swarm_from_swarms_json(swarm_candidate: Any) -> SwarmsJSONSwarm:
    """
    Build a `SwarmsJSONSwarm` from a candidate.
    """
    validate_swarm_from_swarms_json(swarm_candidate)
    return SwarmsJSONSwarm(
        name=swarm_candidate["name"],
        version=swarm_candidate["version"],
        description=swarm_candidate.get("description", ""),
        keywords=swarm_candidate.get("keywords", []),
        public=swarm_candidate.get("public", False),
        entrypoint=swarm_candidate["entrypoint"],
        agents=[
            build_agent_from_swarms_json(agent) for agent in swarm_candidate["agents"]
        ],
        actions=[
            build_action_from_swarms_json(action)
            for action in swarm_candidate["actions"]
        ],
        action_imports=swarm_candidate.get("action_imports", []),
        enable_interswarm=swarm_candidate.get("enable_interswarm", False),
        breakpoint_tools=swarm_candidate.get("breakpoint_tools", []),
        exclude_tools=swarm_candidate.get("exclude_tools", []),
        enable_db_agent_histories=swarm_candidate.get(
            "enable_db_agent_histories", False
        ),
    )


def validate_agent_from_swarms_json(agent_candidate: Any) -> None:
    """
    Ensure the candidate is a valid `SwarmsJSONAgent`.
    """
    if not isinstance(agent_candidate, dict):
        raise ValueError(
            f"agent candidate must be a dict, actually got {type(agent_candidate)}"
        )

    REQUIRED_FIELDS: dict[str, type] = {
        "name": str,
        "factory": str,
        "comm_targets": list,
        "agent_params": dict,
    }

    OPTIONAL_FIELDS: dict[str, type] = {
        "enable_entrypoint": bool,
        "enable_interswarm": bool,
        "can_complete_tasks": bool,
        "tool_format": str,
        "actions": list,
    }

    for field, field_type in REQUIRED_FIELDS.items():
        if field not in agent_candidate:
            raise ValueError(f"agent candidate must contain a '{field}' field")
        if not isinstance(agent_candidate[field], field_type):
            raise ValueError(
                f"agent candidate field '{field}' must be a {field_type.__name__}, actually got {type(agent_candidate[field])}"
            )

    for field, field_type in OPTIONAL_FIELDS.items():
        if field not in agent_candidate:
            continue
        if not isinstance(agent_candidate[field], field_type):
            raise ValueError(
                f"agent candidate field '{field}' must be a {field_type.__name__}, actually got {type(agent_candidate[field])}"
            )

    # Warn about deprecated tool_format placement
    if "agent_params" in agent_candidate:
        if "tool_format" in agent_candidate["agent_params"]:
            warnings.warn(
                f"agent '{agent_candidate.get('name', '?')}' has tool_format inside agent_params; "
                "this is deprecated, use top-level tool_format instead",
                DeprecationWarning,
                stacklevel=2,
            )

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
        exclude_tools=agent_candidate.get("exclude_tools", []),
    )


def validate_action_from_swarms_json(action_candidate: Any) -> None:
    """
    Ensure the candidate is a valid `SwarmsJSONAction`.
    """
    if not isinstance(action_candidate, dict):
        raise ValueError(
            f"action candidate must be a dict, actually got {type(action_candidate)}"
        )

    REQUIRED_FIELDS: dict[str, type] = {
        "name": str,
        "description": str,
        "parameters": dict,
        "function": str,
    }

    OPTIONAL_FIELDS: dict[str, type] = {}

    for field, field_type in REQUIRED_FIELDS.items():
        if field not in action_candidate:
            raise ValueError(f"action candidate must contain a '{field}' field")
        if not isinstance(action_candidate[field], field_type):
            raise ValueError(
                f"action candidate field '{field}' must be a {field_type.__name__}, actually got {type(action_candidate[field])}"
            )

    for field, field_type in OPTIONAL_FIELDS.items():
        if field not in action_candidate:
            continue
        if not isinstance(action_candidate[field], field_type):
            raise ValueError(
                f"action candidate field '{field}' must be a {field_type.__name__}, actually got {type(action_candidate[field])}"
            )

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
