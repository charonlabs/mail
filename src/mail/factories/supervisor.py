from typing import Any, Literal

from .base import AgentFunction, base_agent_factory
from ..tools import create_supervisor_tools


def supervisor_factory(
    user_token: str,
    llm: str,
    comm_targets: list[str],
    agent_params: dict[str, Any],
    tools: list[dict[str, Any]],
    system: str,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    name: str = "supervisor",
) -> AgentFunction:
    can_complete_tasks = agent_params.get("can_complete_tasks", True)
    enable_interswarm = agent_params.get("enable_interswarm", False)
    tools = create_supervisor_tools(comm_targets, can_complete_tasks, enable_interswarm)
    agent = base_agent_factory(
        user_token=user_token,
        llm=llm,
        comm_targets=comm_targets,
        agent_params=agent_params,
        tools=tools,
        system=system,
        reasoning_effort=reasoning_effort,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        memory=memory,
        name=name,
    )
    return agent
