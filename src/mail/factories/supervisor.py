# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

from typing import Any, Literal

from openai.resources.responses.responses import _make_tools

from mail.core.tools import create_supervisor_tools, pydantic_function_tool
from mail.factories.base import AgentFunction, base_agent_factory


def supervisor_factory(
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
    name: str = "supervisor",
    enable_entrypoint: bool = True,
    enable_interswarm: bool = False,
    can_complete_tasks: bool = True,
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
    """
    Create a `supervisor` agent function.
    """
    _debug_include_intraswarm = True

    if len(comm_targets) == 0:
        _debug_include_intraswarm = False

    # parse the user-provided tools
    parsed_tools: list[dict[str, Any]] = []
    if len(tools) == 0:
        parsed_tools = []
    elif not isinstance(tools[0], dict):
        parsed_tools = [pydantic_function_tool(tool) for tool in tools]
        if tool_format == "responses":
            parsed_tools = _make_tools(parsed_tools)
    else:
        parsed_tools = tools

    # add supervisor tools to user-provided tools
    parsed_tools += create_supervisor_tools(
        comm_targets,
        can_complete_tasks,
        enable_interswarm,
        style=tool_format,
        _debug_include_intraswarm=_debug_include_intraswarm,
    )

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
        tool_format=tool_format,
        name=name,
        enable_entrypoint=enable_entrypoint,
        enable_interswarm=enable_interswarm,
        _debug_include_mail_tools=_debug_include_intraswarm,
    )

    return agent
