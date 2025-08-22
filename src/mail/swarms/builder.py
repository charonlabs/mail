import importlib
import json
from typing import Any

from ..core import MAIL
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

def build_swarm_from_json_str(json_swarm: str, name: str) -> Swarm:
    try:
        swarms = json.loads(json_swarm)

        swarm_agents: list[Agent] = []
        for swarm in swarms:
            if swarm["name"] == name:
                for agent in swarm["agents"]:
                    swarm_agents.append(
                        Agent(
                            name=agent["name"],
                            factory=read_python_string(agent["factory"]),
                            llm=agent["llm"],
                            system=read_python_string(agent["system"]),
                            comm_targets=agent["comm_targets"],
                            agent_params=agent["agent_params"]
                        )
                    )
                
                return Swarm(name=name, agents=swarm_agents)
        raise ValueError(f"Swarm {name} not found in swarms JSON!")
    except Exception as e:
        raise Exception(f"Failed to build swarm from JSON string: {e}") from e

if __name__ == "__main__":
    json.loads