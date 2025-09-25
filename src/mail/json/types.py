# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any, Literal, TypedDict


class SwarmsJSONFile(TypedDict):
    """
    A standardized container for MAIL swarms and their configuration.
    """

    swarms: list["SwarmsJSONSwarm"]


class SwarmsJSONSwarm(TypedDict):
    """
    A MAIL swarm and its configuration, following the `swarms.json` format.
    """

    name: str
    """The swarm's name."""
    version: str
    """The version of `mail` to build this swarm with."""
    entrypoint: str
    """The name of the swarm's default entrypoint agent."""
    enable_interswarm: bool  # default: False
    """Whether to enable interswarm communication for this swarm."""
    agents: list["SwarmsJSONAgent"]
    """The agents in this swarm."""
    actions: list["SwarmsJSONAction"]
    """The actions in this swarm."""


class SwarmsJSONAgent(TypedDict):
    """
    A MAIL agent and its configuration, following the `swarms.json` format.
    """

    name: str
    """The agent's name."""
    factory: str
    """The agent's factory function as a Python import string."""
    comm_targets: list[str]
    """The names of the agents this agent can communicate with."""
    enable_entrypoint: bool  # default: False
    """Whether this agent can be used as a swarm entrypoint."""
    enable_interswarm: bool  # default: False
    """Whether this agent can communicate with other swarms."""
    can_complete_tasks: bool  # default: False
    """Whether this agent can complete tasks."""
    tool_format: Literal["completions", "responses"]  # default: "responses"
    """The format of the tools this agent can use."""
    actions: list[str]  # default: []
    """The names of the actions this agent can use."""
    agent_params: dict[str, Any]
    """The parameters for this agent."""


class SwarmsJSONAction(TypedDict):
    """
    A MAIL action and its configuration, following the `swarms.json` format.
    """

    name: str
    """The action's name."""
    description: str
    """The action's description."""
    parameters: dict[str, Any]
    """The parameters for this action."""
    function: str
    """The action's function as a Python import string."""
