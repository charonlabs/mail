# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import warnings
from collections.abc import Awaitable
from typing import Any, Literal

from mail.core.agents import AgentOutput
from mail.factories import AgentFunction
from mail.factories.base import LiteLLMAgentFunction

math_agent_params = {
    "llm": "openai/gpt-5-mini",
    "system": "mail.examples.math_dummy.prompts:SYSPROMPT",
}


def factory_math_dummy(
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
    name: str = "math",
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
    warnings.warn(
        "`mail.examples.math_dummy:factory_math_dummy` is deprecated and will be removed in a future version. "
        "Use `mail.examples.math_dummy:LiteLLMMathFunction` instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    litellm_math = LiteLLMMathFunction(
        name=name,
        comm_targets=comm_targets,
        tools=tools,
        llm=llm,
        system=system,
        user_token=user_token,
        enable_entrypoint=enable_entrypoint,
        enable_interswarm=enable_interswarm,
        can_complete_tasks=can_complete_tasks,
        reasoning_effort=reasoning_effort,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        memory=memory,
        use_proxy=use_proxy,
        tool_format=tool_format,
        exclude_tools=exclude_tools,
    )

    async def run(
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Execute the LiteLLM-based math agent function.
        """
        return await litellm_math(messages, tool_choice)

    return run


class LiteLLMMathFunction(LiteLLMAgentFunction):
    """
    Class that represents a LiteLLM-based math agent function.
    """

    def __init__(
        self,
        name: str,
        comm_targets: list[str],
        tools: list[dict[str, Any]],
        llm: str,
        system: str,
        user_token: str = "",
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        can_complete_tasks: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
        exclude_tools: list[str] = [],
        reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None,
        thinking_budget: int | None = None,
        max_tokens: int | None = None,
        memory: bool = True,
        use_proxy: bool = True,
        _debug_include_mail_tools: bool = True,
    ) -> None:
        super().__init__(
            name=name,
            comm_targets=comm_targets,
            tools=tools,
            llm=llm,
            system=system,
            user_token=user_token,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            can_complete_tasks=can_complete_tasks,
            tool_format=tool_format,
            exclude_tools=exclude_tools,
            reasoning_effort=reasoning_effort,
            thinking_budget=thinking_budget,
            max_tokens=max_tokens,
            memory=memory,
            use_proxy=use_proxy,
            _debug_include_mail_tools=_debug_include_mail_tools,
        )

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Execute the LiteLLM-based math agent function.
        """
        return super().__call__(messages, tool_choice)
