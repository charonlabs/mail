import importlib
import json
from typing import Any

from ..core import MAIL
from ..factories.action import action_agent_factory
from ..factories.base import AgentFunction, base_agent_factory
from ..factories.supervisor import supervisor_factory
from .swarm import Agent, Swarm
from .utils import create_tools_from_actions, read_python_string


def build_swarm_from_name(name: str) -> Swarm:
    """
    Build a swarm from a name.
    A swarm with this name must exist in swarms.json for this to work.
    """

    with open("swarms.json", "r") as f:
        swarms = json.load(f)

    for swarm in swarms:
        if swarm["name"] == name:
            swarm_agents = []
            for agent in swarm["agents"]:
                # Support new schema: llm/system/actions live under agent_params
                agent_params = agent.get("agent_params", {})
                llm = agent_params.get("llm", agent.get("llm"))
                system_ref = agent_params.get("system", agent.get("system"))
                if llm is None or system_ref is None:
                    raise KeyError(
                        f"agent '{agent.get('name', '<unknown>')}' is missing 'llm' or 'system' in agent_params"
                    )

                actions = agent_params.get("actions", agent.get("actions", []))
                tools = create_tools_from_actions(actions)

                swarm_agents.append(
                    Agent(
                        name=agent["name"],
                        factory=read_python_string(agent["factory"]),
                        llm=llm,
                        system=read_python_string(system_ref),
                        comm_targets=agent["comm_targets"],
                        agent_params=agent_params,
                        tools=tools,
                        reasoning_effort=agent_params.get("reasoning_effort"),
                        thinking_budget=agent_params.get("thinking_budget"),
                        max_tokens=agent_params.get("max_tokens"),
                        memory=agent_params.get("memory", True),
                    )
                )

            return Swarm(
                name=name, agents=swarm_agents, default_entrypoint=swarm["entrypoint"]
            )

    raise ValueError(f"swarm '{name}' not found in swarms.json")


def build_swarm_from_json_str(json_swarm: str) -> Swarm:
    try:
        swarm = json.loads(json_swarm)

        swarm_agents: list[Agent] = []
        for agent in swarm["agents"]:
            agent_params = agent.get("agent_params", {})
            llm = agent_params.get("llm", agent.get("llm"))
            system_ref = agent_params.get("system", agent.get("system"))
            if llm is None or system_ref is None:
                raise KeyError(
                    f"agent '{agent.get('name', '<unknown>')}' is missing 'llm' or 'system' in agent_params"
                )

            actions = agent_params.get("actions", agent.get("actions", []))
            tools = create_tools_from_actions(actions)
            swarm_agents.append(
                Agent(
                    name=agent["name"],
                    factory=read_python_string(agent["factory"]),
                    llm=llm,
                    system=read_python_string(system_ref),
                    comm_targets=agent["comm_targets"],
                    agent_params=agent_params,
                    tools=tools,
                    reasoning_effort=agent_params.get("reasoning_effort"),
                    thinking_budget=agent_params.get("thinking_budget"),
                    max_tokens=agent_params.get("max_tokens"),
                    memory=agent_params.get("memory", True),
                )
            )

        return Swarm(
            name=swarm["name"],
            agents=swarm_agents,
            default_entrypoint=swarm["entrypoint"],
        )
    except Exception as e:
        raise Exception(f"Failed to build swarm from JSON string: {e}") from e


if __name__ == "__main__":
    json.loads
