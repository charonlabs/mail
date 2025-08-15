import json
from typing import Any, Literal

from acp.swarm_registry import SwarmRegistry
from pydantic import BaseModel

from ..core import ACP
from ..factories.action import ActionFunction
from ..factories.base import AgentFunction
from .utils import read_python_string


class Agent(BaseModel):
    name: str
    factory: AgentFunction
    llm: str
    system: str
    comm_targets: list[str]
    agent_params: dict[str, Any]
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

    def instantiate(
        self,
        user_token: str,
        swarm_name: str,
        swarm_registry: SwarmRegistry,
        enable_interswarm: bool,
    ) -> ACP:
        """
        Create an ACP instance for this swarm that is ready to be used.
        """
        agents, actions = self._build_acp_dicts(user_token)

        return ACP(
            agents=agents,
            actions=actions,
            user_token=user_token,
            swarm_name=swarm_name,
            swarm_registry=swarm_registry,
            enable_interswarm=enable_interswarm,
        )

    def _build_acp_dicts(
        self, user_token: str
    ) -> tuple[dict[str, AgentFunction], dict[str, ActionFunction]]:
        """
        Build dictionaries of agents and actions from the swarm.
        """
        agents: dict[str, AgentFunction] = {}
        actions: dict[str, ActionFunction] = {}

        for agent in self.agents:
            agents[agent.name] = agent.factory(
                user_token=user_token,
                llm=agent.llm,
                system=agent.system,
                comm_targets=agent.comm_targets,
                agent_params=agent.agent_params,
                reasoning_effort=agent.reasoning_effort,
                thinking_budget=agent.thinking_budget,
                max_tokens=agent.max_tokens,
                memory=agent.memory,
            )
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
