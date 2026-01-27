# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import warnings
from abc import abstractmethod
from collections.abc import Awaitable
from typing import Any, Literal

from openai.resources.responses.responses import _make_tools

from mail.core.agents import AgentFunction, AgentOutput
from mail.core.tools import (
    create_supervisor_tools,
    pydantic_function_tool,
)
from mail.factories.base import (
    LiteLLMAgentFunction,
    MAILAgentFunction,
)


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
    exclude_tools: list[str] = [],
    # instance params
    # ...
    # internal params
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    use_proxy: bool = True,
    stream_tokens: bool = False,
    default_tool_choice: str | dict[str, str] | None = None,
) -> AgentFunction:
    """
    Create a `supervisor` agent function.
    """
    warnings.warn(
        "`mail.factories.supervisor:supervisor_factory` is deprecated and will be removed in a future version. "
        "Use `mail.factories.supervisor:LiteLLMSupervisorFunction` instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    litellm_supervisor = LiteLLMSupervisorFunction(
        name=name,
        comm_targets=comm_targets,
        tools=tools,
        llm=llm,
        system=system,
        user_token=user_token,
        enable_entrypoint=enable_entrypoint,
        enable_interswarm=enable_interswarm,
        can_complete_tasks=True,  # supervisor can always complete tasks; param kept for compatibility
        reasoning_effort=reasoning_effort,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        memory=memory,
        use_proxy=use_proxy,
        tool_format=tool_format,
        exclude_tools=exclude_tools,
        stream_tokens=stream_tokens,
        default_tool_choice=default_tool_choice,
    )

    async def run(
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Execute the MAIL-compatible supervisor function.
        """
        return await litellm_supervisor(messages, tool_choice)

    return run


class SupervisorFunction(MAILAgentFunction):
    """
    Class representing a MAIL-compatible supervisor function.
    """

    def __init__(
        self,
        name: str,
        comm_targets: list[str],
        tools: list[dict[str, Any]],
        can_complete_tasks: bool = True,
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
        exclude_tools: list[str] = [],
        **kwargs: Any,
    ) -> None:
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
            targets=comm_targets,
            can_complete_tasks=True,  # supervisor can always complete tasks; param kept for compatibility
            enable_interswarm=enable_interswarm,
            exclude_tools=exclude_tools,
            style=tool_format,
            _debug_include_intraswarm=_debug_include_intraswarm,
        )

        super().__init__(
            name=name,
            comm_targets=comm_targets,
            tools=parsed_tools,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            can_complete_tasks=True,  # supervisor can always complete tasks; param kept for compatibility
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
        Execute the MAIL-compatible supervisor function.
        """
        pass


class LiteLLMSupervisorFunction(SupervisorFunction):
    """
    Class representing a MAIL-compatible, LiteLLM-based supervisor function.
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
        can_complete_tasks: bool = True,
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
            can_complete_tasks=True,  # supervisor can always complete tasks; param kept for compatibility
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
        self.supervisor_fn = LiteLLMAgentFunction(
            name=self.name,
            comm_targets=self.comm_targets,
            tools=self.tools,
            llm=self.llm,
            system=self.system,
            enable_entrypoint=self.enable_entrypoint,
            enable_interswarm=self.enable_interswarm,
            can_complete_tasks=True,
            tool_format=self.tool_format,
            exclude_tools=self.exclude_tools,
            reasoning_effort=self.reasoning_effort,
            thinking_budget=self.thinking_budget,
            max_tokens=self.max_tokens,
            memory=self.memory,
            use_proxy=self.use_proxy,
            _debug_include_mail_tools=self._debug_include_mail_tools,
            stream_tokens=self.stream_tokens,
            default_tool_choice=self.default_tool_choice,
        )

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Execute a LiteLLM-based supervisor function.
        """
        return self.supervisor_fn(
            messages=messages,
            tool_choice=tool_choice,
        )
