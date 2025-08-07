from typing import Any, Literal

from pydantic import BaseModel

from acp.core import ACP
from acp.factories.action import ActionFunction
from acp.factories.base import AgentFunction


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

    def instantiate(self, user_token: str) -> ACP:
        """
        Create an ACP instance for this swarm that is ready to be used.
        """
        agents, actions = self._build_acp_dicts(user_token)

        return ACP(agents=agents, actions=actions, user_token=user_token)

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

        try:
            for action in agent_params["actions"]:
                actions[action["name"]] = action["function"]
        except KeyError:
            return {}
        
        return actions