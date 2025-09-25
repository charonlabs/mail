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


def load_swarms_from_swarms_json(contents: list[Any]) -> list["SwarmsJSONSwarm"]:
    """
    Load a list of `SwarmsJSONSwarm` from a list of `SwarmsJSONFile` contents.
    """
    for swarm in contents:
        if not validate_swarm_from_swarms_json(swarm):
            raise ValueError(f"swarm {swarm['name']} is not valid")

    return [build_swarm_from_swarms_json(swarm) for swarm in contents]


def validate_swarms_json_swarm(swarm: SwarmsJSONSwarm) -> bool:
    """
    Validate a `SwarmsJSONSwarm` is valid.
    """
    raise NotImplementedError("Not implemented")


def build_swarm_from_swarms_json(swarm: SwarmsJSONSwarm) -> "SwarmsJSONSwarm":
    """
    Build a `SwarmsJSONSwarm` from a `SwarmsJSONSwarm` contents.
    """
    raise NotImplementedError("Not implemented")


def validate_agent_from_swarms_json(agent: SwarmsJSONAgent) -> bool:
    """
    Validate a `SwarmsJSONAgent` is valid.
    """
    raise NotImplementedError("Not implemented")


def build_agent_from_swarms_json(agent: SwarmsJSONAgent) -> "SwarmsJSONAgent":
    """
    Build a `SwarmsJSONAgent` from a `SwarmsJSONAgent` contents.
    """
    raise NotImplementedError("Not implemented")


def validate_action_from_swarms_json(action: SwarmsJSONAction) -> bool:
    """
    Validate a `SwarmsJSONAction` is valid.
    """
    raise NotImplementedError("Not implemented")


def validate_file_from_swarms_json(file: SwarmsJSONFile) -> bool:
    """
    Validate a `SwarmsJSONFile` is valid.
    """
    raise NotImplementedError("Not implemented")


def build_action_from_swarms_json(action: SwarmsJSONAction) -> "SwarmsJSONAction":
    """
    Build a `SwarmsJSONAction` from a `SwarmsJSONAction` contents.
    """
    raise NotImplementedError("Not implemented")