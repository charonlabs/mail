from collections.abc import Callable
import json
from typing import Any, Literal

from ..swarm_registry import SwarmRegistry
from pydantic import BaseModel

from ..core import MAIL
from ..factories.action import ActionFunction
from ..factories.base import AgentFunction
from .utils import read_python_string


class Agent(BaseModel):
    name: str
    factory: Callable[
        [
            str,
            str,
            list[str],
            dict[str, Any],
            list[dict[str, Any]],
            str,
            Literal["low", "medium", "high"] | None,
            int | None,
            int | None,
            bool,
            str,
        ],
        AgentFunction,
    ]
    llm: str
    system: str
    comm_targets: list[str]
    agent_params: dict[str, Any]
    tools: list[dict[str, Any]]
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    thinking_budget: int | None = None
    max_tokens: int | None = None
    memory: bool = True


class Action(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    function: ActionFunction


class Swarm(BaseModel):
    name: str
    agents: list[Agent]
    default_entrypoint: str

    def instantiate(
        self,
        user_id: str,
        user_token: str,
        swarm_name: str,
        swarm_registry: SwarmRegistry,
        enable_interswarm: bool,
    ) -> MAIL:
        """
        Create a MAIL instance for this swarm that is ready to be used.
        """
        agents, actions = self._build_mail_dicts(user_token)

        return MAIL(
            agents=agents,
            actions=actions,
            user_id=user_id,
            swarm_name=swarm_name,
            swarm_registry=swarm_registry,
            enable_interswarm=enable_interswarm,
            entrypoint=self.default_entrypoint,
        )

    def _build_mail_dicts(
        self, user_token: str
    ) -> tuple[dict[str, AgentFunction], dict[str, ActionFunction]]:
        """
        Build dictionaries of agents and actions from the swarm.
        """
        agents: dict[str, AgentFunction] = {}
        actions: dict[str, ActionFunction] = {}

        for agent in self.agents:
            factory = agent.factory
            agents[agent.name] = factory(
                user_token=user_token,
                llm=agent.llm,
                comm_targets=agent.comm_targets,
                agent_params=agent.agent_params,
                tools=agent.tools,
                system=agent.system,
                reasoning_effort=agent.reasoning_effort,
                thinking_budget=agent.thinking_budget,
                max_tokens=agent.max_tokens,
                memory=agent.memory,
                name=agent.name,
            )  # type: ignore
            actions.update(self._build_actions(agent.agent_params))

        return agents, actions

    def _build_actions(self, agent_params: dict[str, Any]) -> dict[str, ActionFunction]:
        """
        Build a dictionary of actions from the agent parameters.
        """
        actions: dict[str, ActionFunction] = {}
        actions_list = agent_params.get("actions", [])
        for action in actions_list:
            actions[action["name"]] = read_python_string(action["function"])
        return actions
