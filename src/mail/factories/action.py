# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import warnings
from abc import abstractmethod
from collections.abc import Awaitable
from typing import Any, Literal

from openai import pydantic_function_tool
from openai.resources.responses.responses import _make_tools

from mail.core.agents import AgentFunction, AgentOutput
from mail.factories.base import (
    LiteLLMAgentFunction,
    MAILAgentFunction,
)


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
    warnings.warn(
        "`mail.factories.action:action_agent_factory` is deprecated and will be removed in a future version. "
        "Use `mail.factories.action:LiteLLMActionAgentFunction` instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    litellm_action_agent = LiteLLMActionAgentFunction(
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

    async def run(
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Execute the LiteLLM-based action agent function.
        """
        return await litellm_action_agent(messages, tool_choice)

    return run


class ActionAgentFunction(MAILAgentFunction):
    """
    Class representing a MAIL-compatible action agent function.
    """

    def __init__(
        self,
        name: str,
        comm_targets: list[str],
        tools: list[dict[str, Any]],
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        can_complete_tasks: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
        exclude_tools: list[str] = [],
        **kwargs: Any,
    ) -> None:
        # ensure that the action tools are in the correct format
        parsed_tools: list[dict[str, Any]] = []
        if not isinstance(tools[0], dict):
            parsed_tools = [pydantic_function_tool(tool) for tool in tools]  # type: ignore
            if tool_format == "responses":
                parsed_tools = _make_tools(parsed_tools)  # type: ignore

        else:
            parsed_tools = tools  # type: ignore

        super().__init__(
            name=name,
            comm_targets=comm_targets,
            tools=parsed_tools,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            can_complete_tasks=can_complete_tasks,
            tool_format=tool_format,
            exclude_tools=exclude_tools,
            **kwargs,
        )

    @abstractmethod
    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Execute the MAIL-compatible agent function.
        """
        pass


class LiteLLMActionAgentFunction(ActionAgentFunction):
    """
    Class representing a MAIL-compatible, LiteLLM-based action agent function.
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
        stream_tokens: bool = False,
        default_tool_choice: str | dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            comm_targets=comm_targets,
            tools=tools,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            can_complete_tasks=can_complete_tasks,
            tool_format=tool_format,
            exclude_tools=exclude_tools,
        )
        self.llm = llm
        self.system = system
        self.user_token = user_token
        self.reasoning_effort = reasoning_effort
        self.thinking_budget = thinking_budget
        self.max_tokens = max_tokens
        self.memory = memory
        self.use_proxy = use_proxy
        self._debug_include_mail_tools = _debug_include_mail_tools
        self.stream_tokens = stream_tokens
        self.default_tool_choice = default_tool_choice
        self.action_agent_fn = LiteLLMAgentFunction(
            llm=self.llm,
            comm_targets=self.comm_targets,
            tools=self.tools,
            system=self.system,
            user_token=self.user_token,
            reasoning_effort=self.reasoning_effort,
            thinking_budget=self.thinking_budget,
            max_tokens=self.max_tokens,
            memory=self.memory,
            use_proxy=self.use_proxy,
            can_complete_tasks=self.can_complete_tasks,
            tool_format=self.tool_format,
            name=self.name,
            enable_entrypoint=self.enable_entrypoint,
            enable_interswarm=self.enable_interswarm,
            exclude_tools=self.exclude_tools,
            _debug_include_mail_tools=self._debug_include_mail_tools,
            stream_tokens=self.stream_tokens,
        )

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Execute a LiteLLM-based action agent function.
        """
        # Use default_tool_choice if set, otherwise use the passed tool_choice
        effective_tool_choice = (
            self.default_tool_choice
            if self.default_tool_choice is not None
            else tool_choice
        )
        return self.action_agent_fn(
            messages=messages,
            tool_choice=effective_tool_choice,
        )
