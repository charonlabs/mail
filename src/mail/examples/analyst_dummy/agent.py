from typing import Any, Literal

from mail.factories import (
    AgentFunction,
    base_agent_factory,
)


def factory_analyst_dummy(
    # REQUIRED
    # top-level params
    comm_targets: list[str],
    tools: list[dict[str, Any]],
    # instance params
    user_token: str,
    # internal params
    llm: str,
    system: str,
    # OPTIONAL
    # top-level params
    name: str = "analyst",
    enable_entrypoint: bool = False,
    enable_interswarm: bool = False,
    tool_format: Literal["completions", "responses"] = "responses",
    # instance params
    # ...
    # internal params
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    use_proxy: bool = True,
) -> AgentFunction:
    return base_agent_factory(
        user_token=user_token,
        llm=llm,
        comm_targets=comm_targets,
        tools=tools,
        system=system,
        reasoning_effort=reasoning_effort,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        memory=memory,
        name=name,
        enable_entrypoint=enable_entrypoint,
        enable_interswarm=enable_interswarm,
        tool_format=tool_format,
        use_proxy=use_proxy,
    )
