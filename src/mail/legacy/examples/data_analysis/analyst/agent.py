# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Analyst agent for the Data Analysis swarm."""

from collections.abc import Awaitable
from typing import Any, Literal

from mail.core.agents import AgentOutput
from mail.factories.base import LiteLLMAgentFunction


class LiteLLMAnalystFunction(LiteLLMAgentFunction):
    """
    Lead analyst agent that orchestrates the data analysis workflow.

    This agent serves as the entry point for data analysis requests and
    coordinates processor, statistics, and reporter agents.
    """

    def __init__(
        self,
        name: str,
        comm_targets: list[str],
        tools: list[dict[str, Any]],
        llm: str,
        system: str,
        user_token: str = "",
        enable_entrypoint: bool = True,
        enable_interswarm: bool = False,
        can_complete_tasks: bool = True,
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
        """Execute the analyst agent function."""
        return super().__call__(messages, tool_choice)
