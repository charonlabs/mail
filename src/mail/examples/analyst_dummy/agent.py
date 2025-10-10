# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import warnings
from collections.abc import Awaitable
from typing import Any, Literal

from mail.core.agents import AgentOutput
from mail.factories import AgentFunction
from mail.factories.base import LiteLLMAgentFunction

analyst_agent_params = {
    "llm": "openai/gpt-5-mini",
    "system": "mail.examples.analyst_dummy.prompts:SYSPROMPT",
}


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
        "`mail.examples.analyst_dummy:factory_analyst_dummy` is deprecated and will be removed in a future version. "
        "Use `mail.examples.analyst_dummy:LiteLLMAnalystFunction` instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    litellm_analyst = LiteLLMAnalystFunction(
        name=name,
        comm_targets=comm_targets,
        tools=tools,
        llm=llm,
        system=system,
        user_token=user_token,
        enable_entrypoint=enable_entrypoint,
        enable_interswarm=enable_interswarm,
        reasoning_effort=reasoning_effort,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        memory=memory,
        use_proxy=use_proxy,
        can_complete_tasks=can_complete_tasks,
        tool_format=tool_format,
        exclude_tools=exclude_tools,
    )

    async def run(
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Execute the LiteLLM-based analyst agent function.
        """
        return await litellm_analyst(messages, tool_choice)

    return run


class LiteLLMAnalystFunction(LiteLLMAgentFunction):
    """
    Class that represents a LiteLLM-based analyst agent function.
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
        Execute the LiteLLM-based analyst agent function.
        """
        return super().__call__(messages, tool_choice)
