# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

from typing import Any, Literal

from openai import pydantic_function_tool
from openai.resources.responses.responses import _make_tools

from mail.core.agents import AgentFunction
from mail.factories.base import base_agent_factory


def action_agent_factory(
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
    name: str = "action",
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
    _debug_include_mail_tools: bool = True,
) -> AgentFunction:
    # ensure that the action tools are in the correct format
    parsed_tools: list[dict[str, Any]] = []
    if not isinstance(tools[0], dict):
        parsed_tools = [pydantic_function_tool(tool) for tool in tools]  # type: ignore
        if tool_format == "responses":
            parsed_tools = _make_tools(parsed_tools)  # type: ignore

    else:
        parsed_tools = tools  # type: ignore

    agent = base_agent_factory(
        user_token=user_token,
        llm=llm,
        comm_targets=comm_targets,
        tools=parsed_tools,
        system=system,
        reasoning_effort=reasoning_effort,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        memory=memory,
        use_proxy=use_proxy,
        can_complete_tasks=can_complete_tasks,
        tool_format=tool_format,
        name=name,
        enable_entrypoint=enable_entrypoint,
        enable_interswarm=enable_interswarm,
        exclude_tools=exclude_tools,
        _debug_include_mail_tools=_debug_include_mail_tools,
    )
    return agent
