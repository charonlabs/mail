import importlib
import json
from typing import Any

from ..core import ACP
from ..factories.action import action_agent_factory
from ..factories.base import AgentFunction, base_agent_factory
from ..factories.supervisor import supervisor_factory
from .swarm import Agent, Swarm
from .utils import read_python_string


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
                swarm_agents.append(
                    Agent(
                        name=agent["name"],
                        factory=read_python_string(agent["factory"]),
                        llm=agent["llm"],
                        system=read_python_string(agent["system"]),
                        comm_targets=agent["comm_targets"],
                        agent_params=agent["agent_params"],
                    )
                )

            return Swarm(name=name, agents=swarm_agents)

    raise ValueError(f"swarm '{name}' not found in swarms.json")