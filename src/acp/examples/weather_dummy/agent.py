from typing import Any, Literal

from acp.factories.base import AgentFunction
from acp.factories.action import action_agent_factory


def factory_weather_dummy(
    user_token: str,
    llm: str,
    system: str,
    comm_targets: list[str],
    agent_params: dict[str, Any],
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    name: str = "weather",
) -> AgentFunction:
    action_tools = agent_params["actions"]

    return action_agent_factory(
        user_token=user_token,
        llm=llm,
        comm_targets=comm_targets,
        agent_params=agent_params,
        action_tools=action_tools,
        system=system,
        reasoning_effort=reasoning_effort,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        memory=memory,
        name=name,
    )