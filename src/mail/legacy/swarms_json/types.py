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
    description: str  # default: ""
    """The description of the swarm."""
    keywords: list[str]  # default: []
    """The keywords of the swarm."""
    public: bool  # default: False
    """Whether this swarm is publicly accessible."""
    entrypoint: str
    """The name of the swarm's default entrypoint agent."""
    enable_interswarm: bool  # default: False
    """Whether to enable interswarm communication for this swarm."""
    action_imports: list[str]  # default: []
    """Python import strings that resolve to pre-built MAILAction instances."""
    agents: list["SwarmsJSONAgent"]
    """The agents in this swarm."""
    actions: list["SwarmsJSONAction"]
    """The actions in this swarm."""
    breakpoint_tools: list[str]  # default: []
    """The tools that can be used to breakpoint the swarm."""
    exclude_tools: list[str]  # default: []
    """The names of MAIL tools that should not be available to the swarm."""
    enable_db_agent_histories: bool  # default: False
    """Whether to enable database persistence for agent histories."""


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
    exclude_tools: list[str]  # default: []
    """The names ofMAIL tools that should not be available to this agent."""


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
