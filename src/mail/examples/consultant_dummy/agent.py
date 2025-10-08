# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any, Literal

from mail.factories import (
    AgentFunction,
    base_agent_factory,
)

consultant_agent_params = {
    "llm": "openai/gpt-5-mini",
    "system": "mail.examples.consultant_dummy.prompts:SYSPROMPT",
}


def factory_consultant_dummy(
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
    name: str = "consultant",
    enable_entrypoint: bool = False,
    enable_interswarm: bool = False,
    can_complete_tasks: bool = False,
    tool_format: Literal["completions", "responses"] = "responses",
    exclude_tools: list[str] = [],
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
        can_complete_tasks=can_complete_tasks,
        tool_format=tool_format,
        exclude_tools=exclude_tools,
        use_proxy=use_proxy,
    )
