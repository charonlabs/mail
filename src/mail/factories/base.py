# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import asyncio
import logging
import warnings
from abc import abstractmethod
from collections.abc import Awaitable
from typing import Any, Literal

import langsmith as ls
import litellm
import rich
import ujson
from litellm import (
    OutputFunctionToolCall,
    ResponsesAPIResponse,
    acompletion,
    aresponses,
)
from litellm.types.utils import ModelResponse

from mail.core.agents import AgentFunction, AgentOutput
from mail.core.tools import AgentToolCall, create_mail_tools

logger = logging.getLogger("mail.factories.base")


def base_agent_factory(
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
    name: str = "base_agent",
    enable_entrypoint: bool = False,
    enable_interswarm: bool = False,
    can_complete_tasks: bool = False,
    tool_format: Literal["completions", "responses"] = "responses",
    exclude_tools: list[str] = [],
    # instance params
    # ...
    # internal params
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    use_proxy: bool = True,
    stream_tokens: bool = False,
    _debug_include_mail_tools: bool = True,
) -> AgentFunction:
    warnings.warn(
        "`mail.factories.base:base_agent_factory` is deprecated and will be removed in a future version. "
        "Use `mail.factories.base:LiteLLMAgentFunction` instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    litellm_agent = LiteLLMAgentFunction(
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
        stream_tokens=stream_tokens,
        _debug_include_mail_tools=_debug_include_mail_tools,
    )

    async def run(
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Return a MAIL-compatible agent function.
        """

        return await litellm_agent(
            messages=messages,
            tool_choice=tool_choice,
        )

    return run


class MAILAgentFunction:
    """
    Base class representing a MAIL-compatible agent function.
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
        self.name = name
        self.comm_targets = comm_targets
        self.tools = tools
        self.enable_entrypoint = enable_entrypoint
        self.enable_interswarm = enable_interswarm
        self.can_complete_tasks = can_complete_tasks
        self.tool_format = tool_format
        self.exclude_tools = exclude_tools
        self.kwargs = kwargs

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


class LiteLLMAgentFunction(MAILAgentFunction):
    """
    Class representing a MAIL-compatible agent function which calls the LiteLLM API.
    """

    def __init__(
        self,
        name: str,
        comm_targets: list[str],
        tools: list[dict[str, Any]],
        llm: str,
        system: str = "",
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
        stream_tokens: bool = False,
        _debug_include_mail_tools: bool = True,
    ) -> None:
        self.extra_headers: dict[str, str] = {}
        if use_proxy:
            if not llm.startswith("litellm_proxy/"):
                llm = f"litellm_proxy/{llm}"
            self.extra_headers["Authorization"] = f"Bearer {user_token}"

        self.thinking: dict[str, Any] = {
            "type": "disabled",
        }

        if reasoning_effort is not None:
            if thinking_budget is None:
                if reasoning_effort == "minimal":
                    thinking_budget = 2000
                if reasoning_effort == "low":
                    thinking_budget = 4000
                elif reasoning_effort == "medium":
                    thinking_budget = 8000
                elif reasoning_effort == "high":
                    thinking_budget = 16000

        if thinking_budget is not None:
            if max_tokens is None:
                max_tokens = thinking_budget + 4000
            self.thinking = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }

        super().__init__(
            name,
            comm_targets,
            tools,
            enable_entrypoint,
            enable_interswarm,
            can_complete_tasks,
            tool_format,
            exclude_tools,
        )
        self.llm = llm
        self.system = system
        self.user_token = user_token
        self.reasoning_effort = reasoning_effort
        self.thinking_budget = thinking_budget
        self.max_tokens = max_tokens
        self.memory = memory
        self.use_proxy = use_proxy
        self.stream_tokens = stream_tokens
        self._debug_include_mail_tools = _debug_include_mail_tools

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Execute the MAIL-compatible agent function using the LiteLLM API.
        """
        if self.tool_format == "completions":
            return self._run_completions(messages, tool_choice)
        else:
            return self._run_responses(messages, tool_choice)

    async def _preprocess(
        self,
        messages: list[dict[str, Any]],
        style: Literal["completions", "responses"],
        exclude_tools: list[str] = [],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        # set up system prompt
        if not messages[0]["role"] == "system" and not self.system == "":
            messages.insert(0, {"role": "system", "content": self.system})

        # add the agent's tools to the list of tools
        if self._debug_include_mail_tools and len(self.comm_targets) > 0:
            agent_tools = (
                create_mail_tools(
                    self.comm_targets,
                    self.enable_interswarm,
                    style=style,
                    exclude_tools=exclude_tools,
                )
                + self.tools
            )
        else:
            agent_tools = self.tools

        return messages, agent_tools

    async def _run_completions(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Execute a LiteLLM completion-style call on behalf of the MAIL agent.
        """
        litellm.drop_params = True
        messages, agent_tools = await self._preprocess(
            messages, "completions", exclude_tools=self.exclude_tools
        )
        retries = 5

        with ls.trace(
            name=f"{self.name}_completions",
            run_type="llm",
            inputs={
                "messages": messages,
                "tools": agent_tools,
                "thinking": self.thinking,
                "reasoning_effort": self.reasoning_effort,
                "max_tokens": self.max_tokens,
                "tool_choice": tool_choice,
            },
        ) as rt:
            while retries > 0:
                try:
                    if self.stream_tokens:
                        res = await self._stream_completions(
                            messages, agent_tools, tool_choice
                        )
                    else:
                        res = await acompletion(
                            model=self.llm,
                            messages=messages,
                            tools=agent_tools,
                            thinking=self.thinking,
                            reasoning_effort=self.reasoning_effort,
                            max_tokens=self.max_tokens,
                            tool_choice=tool_choice if len(agent_tools) > 0 else None,
                            extra_headers=self.extra_headers,
                        )
                    rt.end(outputs={"output": res})
                    break
                except Exception as e:
                    retries -= 1
                    logger.warning(f"Error running completion: {e}")
                    logger.warning(f"Retrying {retries} more times")
                    await asyncio.sleep(retries)

        msg = res.choices[0].message  # type: ignore
        tool_calls: list[AgentToolCall] = []
        # Normalize assistant message to a dict so we can ensure consistent tool_call ids
        assistant_dict = msg.to_dict()  # type: ignore
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:  # type: ignore
                call_id = tc.id
                tool_calls.append(
                    AgentToolCall(
                        tool_name=tc.function.name,  # type: ignore
                        tool_args=ujson.loads(tc.function.arguments),
                        tool_call_id=call_id,
                        completion=assistant_dict,
                    )
                )
        if len(tool_calls) == 0:
            tool_calls.append(
                AgentToolCall(
                    tool_name="text_output",
                    tool_args={"content": msg.content},
                    tool_call_id="",
                    completion=assistant_dict,
                )
            )

        return msg.content, tool_calls

    async def _stream_completions(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> ModelResponse:
        """
        Stream a LiteLLM completion-style call to the terminal.
        """
        litellm.drop_params = True
        stream = await acompletion(
            model=self.llm,
            messages=messages,
            tools=tools,
            thinking=self.thinking,
            reasoning_effort=self.reasoning_effort,
            max_tokens=self.max_tokens,
            tool_choice=tool_choice if len(tools) > 0 else None,
            extra_headers=self.extra_headers,
            stream=True,
        )
        chunks = []
        is_response = False
        is_reasoning = False
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if getattr(delta, "reasoning_content", None) is not None:
                if not is_reasoning:
                    rich.print(
                        f"\n\n[bold green]{'=' * 21} REASONING {'=' * 21}[/bold green]\n\n"
                    )
                    is_reasoning = True
                rich.print(delta.reasoning_content, end="", flush=True)
            elif getattr(delta, "content", None) is not None:
                if not is_response:
                    rich.print(
                        f"\n\n[bold blue]{'=' * 21} RESPONSE {'=' * 21}[/bold blue]\n\n"
                    )
                    is_response = True
                rich.print(delta.content, end="", flush=True)
            chunks.append(chunk)

        final_completion = litellm.stream_chunk_builder(chunks, messages=messages)
        assert isinstance(final_completion, ModelResponse)
        return final_completion

    async def _run_responses(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Execute a LiteLLM responses-style call on behalf of the MAIL agent.
        """
        litellm.drop_params = True
        messages, agent_tools = await self._preprocess(
            messages, "responses", exclude_tools=self.exclude_tools
        )
        retries = 5
        with ls.trace(
            name=f"{self.name}_responses",
            run_type="llm",
            inputs={
                "messages": messages,
                "tools": agent_tools,
                "thinking": self.thinking,
                "reasoning_effort": self.reasoning_effort,
                "max_tokens": self.max_tokens,
                "tool_choice": tool_choice,
            },
        ) as rt:
            include: list[str] = []
            reasoning: dict[str, Any] = {}
            if litellm.supports_reasoning(self.llm):
                include.append("reasoning.encrypted_content")
                reasoning = {
                    "effort": self.reasoning_effort or "medium",
                    "summary": "auto",
                }
            while retries > 0:
                try:
                    if self.stream_tokens:
                        res = await self._stream_responses(
                            messages, include, reasoning, agent_tools, tool_choice
                        )
                    else:
                        res = await aresponses(
                            input=messages,
                            model=self.llm,
                            max_output_tokens=self.max_tokens,
                            include=include,
                            reasoning=reasoning,
                            tool_choice=tool_choice,
                            tools=agent_tools,
                            extra_headers=self.extra_headers,
                        )
                    rt.end(outputs={"output": res})
                    break
                except Exception as e:
                    retries -= 1
                    logger.warning(f"Error running responses: {e}")
                    logger.warning(f"Retrying {retries} more times")
                    await asyncio.sleep(retries)

        tool_calls: list[OutputFunctionToolCall] = []
        message_chunks: list[str] = []

        for output in res.output:
            if isinstance(output, dict):
                if output["type"] == "function_call":
                    tool_calls.append(output)  # type: ignore
                elif output["type"] == "message":
                    message_chunks.append(output["content"][0]["text"])
            elif output.type == "function_call":
                tool_calls.append(output)  # type: ignore
            elif output.type == "message":
                message_chunks.append(output.content[0].text)  # type: ignore

        agent_tool_calls: list[AgentToolCall] = []
        res_dict = res.model_dump()
        outputs = res_dict["output"]

        if len(tool_calls) > 0:
            # Build assistant.tool_calls and AgentToolCall objects with consistent ids
            for tc in tool_calls:
                assert tc is not None
                assert tc.call_id is not None
                assert tc.name is not None
                assert tc.arguments is not None
                call_id = tc.call_id
                agent_tool_calls.append(
                    AgentToolCall(
                        tool_name=tc.name,
                        tool_args=ujson.loads(tc.arguments),
                        tool_call_id=call_id,
                        # Store the assistant message (with tool_calls) as the completion
                        # so the runtime can append a valid chat message to history.
                        responses=outputs,
                    )
                )
            return "", agent_tool_calls
        else:
            assert len(message_chunks) > 0
            agent_tool_calls.append(
                AgentToolCall(
                    tool_name="text_output",
                    tool_args={"content": message_chunks[0]},
                    tool_call_id="",
                    responses=outputs,
                )
            )

            return message_chunks[0], agent_tool_calls

    async def _stream_responses(
        self,
        messages: list[dict[str, Any]],
        include: list[str],
        reasoning: dict[str, Any],
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> ResponsesAPIResponse:
        """
        Stream a LiteLLM responses-style call to the terminal.
        """
        litellm.drop_params = True
        stream = await aresponses(
            input=messages,
            model=self.llm,
            max_output_tokens=self.max_tokens,
            include=include,
            reasoning=reasoning,
            tool_choice=tool_choice,
            tools=tools,
            extra_headers=self.extra_headers,
            stream=True,
        )

        final_response = None

        async for event in stream:
            match event.type:
                case "response.created":
                    rich.print(
                        f"\n\n[bold green]{'=' * 21} REASONING {'=' * 21}[/bold green]\n\n"
                    )
                case "response.reasoning_summary_text.delta":
                    # Stream reasoning text
                    rich.print(event.delta, end="", flush=True)

                case "response.reasoning_summary_text.done":
                    # Reasoning part complete
                    rich.print("\n\n")

                case "response.output_item.added":
                    if event.item["type"] == "message":
                        rich.print(
                            f"\n\n[bold blue]{'=' * 21} RESPONSE {'=' * 21}[/bold blue]\n\n"
                        )

                case "response.output_text.delta":
                    rich.print(event.delta, end="", flush=True)

                case "response.completed":
                    final_response = event.response

        assert final_response is not None
        assert isinstance(final_response, ResponsesAPIResponse)
        return final_response
