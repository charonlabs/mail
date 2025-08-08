from typing import Awaitable, Callable, Literal, Any

from ..tools import create_message_tool

from .base import AgentFunction, base_agent_factory
from ..swarms.utils import create_tools_from_actions

ActionFunction = Callable[[dict[str, Any]], Awaitable[str]]


def action_agent_factory(
    user_token: str,
    llm: str,
    comm_targets: list[str],
    agent_params: dict[str, Any],
    action_tools: list[dict[str, Any]],
    system: str,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    name: str = "action",
) -> AgentFunction:
    # ensure that the action tools are in the correct format
    action_tools = create_tools_from_actions(action_tools)

    tools = [create_message_tool(comm_targets)] + action_tools
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
