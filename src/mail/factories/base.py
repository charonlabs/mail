# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import asyncio
import logging
import warnings
from abc import abstractmethod
from collections.abc import Awaitable
from typing import Any, Literal

import anthropic
import langsmith as ls
import litellm
import rich
import ujson
from langsmith.wrappers import wrap_anthropic
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
    default_tool_choice: str | dict[str, str] | None = None,
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
        default_tool_choice=default_tool_choice,
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
        default_tool_choice: str | dict[str, str] | None = None,
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
        self.default_tool_choice = default_tool_choice

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Execute the MAIL-compatible agent function using the LiteLLM API.
        """
        # Use default_tool_choice if set, otherwise use the passed tool_choice
        effective_tool_choice = (
            self.default_tool_choice
            if self.default_tool_choice is not None
            else tool_choice
        )
        if self.tool_format == "completions":
            return self._run_completions(messages, effective_tool_choice)
        else:
            return self._run_responses(messages, effective_tool_choice)

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

    def _has_web_search_tools(self, tools: list[dict[str, Any]]) -> bool:
        """Check if any tools are Anthropic web_search built-in tools."""
        return any(t.get("type", "").startswith("web_search") for t in tools)

    def _convert_tools_to_anthropic_format(
        self, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Convert tools from OpenAI/LiteLLM completions format to native Anthropic format.

        OpenAI format:
            {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

        Anthropic format:
            {"name": ..., "description": ..., "input_schema": ...}

        Server tools (like web_search) are passed through as-is.
        """
        anthropic_tools: list[dict[str, Any]] = []

        for tool in tools:
            tool_type = tool.get("type", "")

            # Server tools (web_search, etc.) - pass through as-is
            if tool_type.startswith("web_search"):
                anthropic_tools.append(tool)
                continue

            # OpenAI/LiteLLM completions format - convert to Anthropic format
            if tool_type == "function" and "function" in tool:
                func = tool["function"]
                anthropic_tools.append(
                    {
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {}),
                    }
                )
                continue

            # Already in Anthropic format (has input_schema) - pass through
            if "input_schema" in tool:
                anthropic_tools.append(tool)
                continue

            # Unknown format - try to pass through and let Anthropic API handle it
            logger.warning(f"Unknown tool format, passing through as-is: {tool}")
            anthropic_tools.append(tool)

        return anthropic_tools

    def _convert_messages_to_anthropic_format(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Convert messages from OpenAI/LiteLLM format to native Anthropic format.

        Key transformations:
        1. Tool results: {"role": "tool", "content": ..., "tool_call_id": ...}
           → {"role": "user", "content": [{"type": "tool_result", "tool_use_id": ..., "content": ...}]}

        2. Assistant with tool_calls: {"role": "assistant", "tool_calls": [...]}
           → {"role": "assistant", "content": [{"type": "tool_use", ...}]}

        3. Multiple consecutive tool results are grouped into a single user message
        """
        anthropic_messages: list[dict[str, Any]] = []
        pending_tool_results: list[dict[str, Any]] = []

        def flush_tool_results() -> None:
            """Flush pending tool results into a single user message."""
            if pending_tool_results:
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": pending_tool_results.copy(),
                    }
                )
                pending_tool_results.clear()

        for msg in messages:
            role = msg.get("role", "")

            # Handle tool result messages (OpenAI format)
            if role == "tool":
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }
                # Add is_error if present
                if msg.get("is_error"):
                    tool_result["is_error"] = True
                pending_tool_results.append(tool_result)
                continue

            # Flush any pending tool results before processing other messages
            flush_tool_results()

            # Handle assistant messages
            if role == "assistant":
                content = msg.get("content")
                tool_calls = msg.get("tool_calls", [])

                # Check if already in Anthropic format (content is list of typed blocks)
                # This preserves thinking blocks, tool_use blocks, etc. from previous turns
                if (
                    isinstance(content, list)
                    and content
                    and isinstance(content[0], dict)
                    and "type" in content[0]
                ):
                    # Already Anthropic format - pass through directly
                    anthropic_messages.append(msg)
                    continue

                # Convert from OpenAI format
                content = content or ""
                if tool_calls:
                    # Convert to Anthropic format with tool_use content blocks
                    content_blocks: list[dict[str, Any]] = []

                    # Add text content if present
                    if content:
                        content_blocks.append(
                            {
                                "type": "text",
                                "text": content,
                            }
                        )

                    # Add tool_use blocks
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        # Parse arguments if it's a JSON string
                        args = func.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                import json

                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {"raw": args}

                        content_blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc.get("id", ""),
                                "name": func.get("name", ""),
                                "input": args,
                            }
                        )

                    anthropic_messages.append(
                        {
                            "role": "assistant",
                            "content": content_blocks,
                        }
                    )
                else:
                    # No tool calls - pass through with content normalization
                    if isinstance(content, str):
                        anthropic_messages.append(
                            {
                                "role": "assistant",
                                "content": [{"type": "text", "text": content}]
                                if content
                                else [],
                            }
                        )
                    else:
                        # Already structured content
                        anthropic_messages.append(msg)
                continue

            # Handle user messages
            if role == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    anthropic_messages.append(
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": content}],
                        }
                    )
                else:
                    # Already structured content (could have images, etc.)
                    anthropic_messages.append(msg)
                continue

            # Pass through other messages (shouldn't happen often)
            anthropic_messages.append(msg)

        # Flush any remaining tool results
        flush_tool_results()

        return anthropic_messages

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

        # Route all Anthropic models through native SDK for better support of:
        # - Extended thinking / interleaved thinking
        # - Server-side tools (web_search, code_interpreter)
        # - Full response structure preservation
        if "anthropic" in self.llm.lower():
            if self.stream_tokens:
                return await self._stream_completions_anthropic_native(
                    messages, agent_tools, tool_choice
                )
            else:
                return await self._run_completions_anthropic_native(
                    messages, agent_tools, tool_choice
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

    async def _run_completions_anthropic_native(
        self,
        messages: list[dict[str, Any]],
        agent_tools: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Execute a native Anthropic API call with web_search built-in tools.
        This preserves the full response structure including server_tool_use blocks.
        """
        client = wrap_anthropic(anthropic.AsyncAnthropic())

        # Strip provider prefix from model name
        model = self.llm
        for prefix in ("anthropic/", "litellm_proxy/anthropic/", "litellm_proxy/"):
            if model.startswith(prefix):
                model = model[len(prefix) :]
                break

        # Extract system message - Anthropic expects it as a top-level parameter
        system_content = None
        filtered_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                filtered_messages.append(msg)

        # Convert messages from OpenAI/LiteLLM format to Anthropic format
        # This handles tool results (role: "tool") and tool_calls in assistant messages
        anthropic_messages = self._convert_messages_to_anthropic_format(
            filtered_messages
        )

        # Convert tools to Anthropic format
        anthropic_tools = self._convert_tools_to_anthropic_format(agent_tools)

        # Build request params
        request_params: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "tools": anthropic_tools,
            "max_tokens": self.max_tokens or 4096,
        }

        if system_content:
            request_params["system"] = system_content

        # Add thinking/extended thinking if enabled
        thinking_enabled = self.thinking.get("type") == "enabled"
        if thinking_enabled:
            request_params["thinking"] = self.thinking
            # Enable interleaved thinking for Claude 4 models via beta header
            # This allows Claude to think between tool calls for more sophisticated reasoning
            request_params["extra_headers"] = {
                "anthropic-beta": "interleaved-thinking-2025-05-14"
            }

        # Handle tool_choice
        # IMPORTANT: When thinking is enabled, only "auto" and "none" are supported.
        # Using "any" or forced tool use will cause an error.
        if tool_choice == "required":
            if thinking_enabled:
                # Fall back to "auto" when thinking is enabled - "any" is incompatible
                logger.warning(
                    "tool_choice='required' is incompatible with extended thinking. "
                    "Falling back to tool_choice='auto'."
                )
                request_params["tool_choice"] = {"type": "auto"}
            else:
                request_params["tool_choice"] = {"type": "any"}
        elif tool_choice == "auto":
            request_params["tool_choice"] = {"type": "auto"}
        elif isinstance(tool_choice, dict):
            # Validate dict tool_choice when thinking is enabled
            if thinking_enabled and tool_choice.get("type") in ("any", "tool"):
                logger.warning(
                    f"tool_choice={tool_choice} is incompatible with extended thinking. "
                    "Falling back to tool_choice='auto'."
                )
                request_params["tool_choice"] = {"type": "auto"}
            else:
                request_params["tool_choice"] = tool_choice

        response = await client.messages.create(**request_params)

        # Build assistant message from content blocks for multi-turn conversations
        # This preserves thinking blocks, tool_use, text, etc. in Anthropic format
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": [block.model_dump() for block in response.content],
        }

        # Parse response content blocks
        tool_calls: list[AgentToolCall] = []
        text_chunks: list[str] = []
        thinking_blocks: list[
            dict[str, Any]
        ] = []  # Full blocks with signature for multi-turn
        all_citations: list[dict[str, Any]] = []
        web_search_results: dict[
            str, list[dict[str, Any]]
        ] = {}  # tool_use_id -> results

        for block in response.content:
            block_type = block.type

            if block_type == "thinking":
                # Capture full thinking block (including signature) for multi-turn support
                thinking_blocks.append(
                    {
                        "type": "thinking",
                        "thinking": getattr(block, "thinking", ""),
                        "signature": getattr(block, "signature", ""),
                    }
                )

            elif block_type == "redacted_thinking":
                # Capture redacted thinking blocks - these contain encrypted content
                # that must be passed back unmodified for multi-turn conversations
                thinking_blocks.append(
                    {
                        "type": "redacted_thinking",
                        "data": getattr(block, "data", ""),
                    }
                )

            elif block_type == "server_tool_use":
                # Capture the web search query
                tool_calls.append(
                    AgentToolCall(
                        tool_name="web_search_call",
                        tool_args={
                            "query": block.input.get("query", ""),
                            "status": "completed",
                        },
                        tool_call_id=block.id,
                        completion=assistant_message,
                    )
                )

            elif block_type == "web_search_tool_result":
                # Extract search results and associate with tool call
                results = []
                for result in block.content:
                    if hasattr(result, "url"):
                        results.append(
                            {
                                "url": result.url,
                                "title": getattr(result, "title", ""),
                                "page_age": getattr(result, "page_age", None),
                            }
                        )
                web_search_results[block.tool_use_id] = results

            elif block_type == "text":
                text_chunks.append(block.text)
                # Extract citations if present
                if hasattr(block, "citations") and block.citations:
                    for citation in block.citations:
                        all_citations.append(
                            {
                                "url": getattr(citation, "url", ""),
                                "title": getattr(citation, "title", ""),
                                "cited_text": getattr(citation, "cited_text", ""),
                            }
                        )

            elif block_type == "tool_use":
                # Handle regular tool calls (non-server-side)
                tool_calls.append(
                    AgentToolCall(
                        tool_name=block.name,
                        tool_args=block.input,
                        tool_call_id=block.id,
                        completion=assistant_message,
                    )
                )

        # Update tool calls with their results
        for tc in tool_calls:
            if (
                tc.tool_name == "web_search_call"
                and tc.tool_call_id in web_search_results
            ):
                tc.tool_args["results"] = web_search_results[tc.tool_call_id]

        # Add citations to the response if present
        if all_citations:
            for tc in tool_calls:
                if tc.tool_name == "web_search_call":
                    tc.tool_args["citations"] = all_citations
                    break

        # Add thinking/reasoning content if present
        # Extract text content from thinking blocks (for display), excluding redacted blocks
        thinking_content = "".join(
            b.get("thinking", "")
            for b in thinking_blocks
            if b.get("type") == "thinking"
        )
        if thinking_content or thinking_blocks:
            # Add to the first tool call (usually web_search_call or text_output)
            if tool_calls:
                if thinking_content:
                    tool_calls[0].tool_args["reasoning"] = thinking_content
                # Store full thinking blocks for multi-turn conversations with tool use
                # These must be passed back unmodified to maintain reasoning continuity
                if thinking_blocks:
                    tool_calls[0].tool_args["thinking_blocks"] = thinking_blocks

        content = "".join(text_chunks)

        # If no tool calls, add text_output
        if len(tool_calls) == 0:
            tool_args: dict[str, Any] = {"content": content}
            if thinking_content:
                tool_args["reasoning"] = thinking_content
            if thinking_blocks:
                tool_args["thinking_blocks"] = thinking_blocks
            tool_calls.append(
                AgentToolCall(
                    tool_name="text_output",
                    tool_args=tool_args,
                    tool_call_id="",
                    completion=assistant_message,
                )
            )

        return content, tool_calls

    async def _stream_completions_anthropic_native(
        self,
        messages: list[dict[str, Any]],
        agent_tools: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Stream a native Anthropic API call with web_search built-in tools.
        """
        client = wrap_anthropic(anthropic.AsyncAnthropic())

        # Strip provider prefix from model name
        model = self.llm
        for prefix in ("anthropic/", "litellm_proxy/anthropic/", "litellm_proxy/"):
            if model.startswith(prefix):
                model = model[len(prefix) :]
                break

        # Extract system message - Anthropic expects it as a top-level parameter
        system_content = None
        filtered_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                filtered_messages.append(msg)

        # Convert messages from OpenAI/LiteLLM format to Anthropic format
        # This handles tool results (role: "tool") and tool_calls in assistant messages
        anthropic_messages = self._convert_messages_to_anthropic_format(
            filtered_messages
        )

        # Convert tools to Anthropic format
        anthropic_tools = self._convert_tools_to_anthropic_format(agent_tools)

        # Build request params
        request_params: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "tools": anthropic_tools,
            "max_tokens": self.max_tokens or 4096,
        }

        if system_content:
            request_params["system"] = system_content

        # Add thinking/extended thinking if enabled
        thinking_enabled = self.thinking.get("type") == "enabled"
        if thinking_enabled:
            request_params["thinking"] = self.thinking
            # Enable interleaved thinking for Claude 4 models via beta header
            # This allows Claude to think between tool calls for more sophisticated reasoning
            request_params["extra_headers"] = {
                "anthropic-beta": "interleaved-thinking-2025-05-14"
            }

        # Handle tool_choice
        # IMPORTANT: When thinking is enabled, only "auto" and "none" are supported.
        # Using "any" or forced tool use will cause an error.
        if tool_choice == "required":
            if thinking_enabled:
                # Fall back to "auto" when thinking is enabled - "any" is incompatible
                logger.warning(
                    "tool_choice='required' is incompatible with extended thinking. "
                    "Falling back to tool_choice='auto'."
                )
                request_params["tool_choice"] = {"type": "auto"}
            else:
                request_params["tool_choice"] = {"type": "any"}
        elif tool_choice == "auto":
            request_params["tool_choice"] = {"type": "auto"}
        elif isinstance(tool_choice, dict):
            # Validate dict tool_choice when thinking is enabled
            if thinking_enabled and tool_choice.get("type") in ("any", "tool"):
                logger.warning(
                    f"tool_choice={tool_choice} is incompatible with extended thinking. "
                    "Falling back to tool_choice='auto'."
                )
                request_params["tool_choice"] = {"type": "auto"}
            else:
                request_params["tool_choice"] = tool_choice

        is_response = False
        is_searching = False
        is_reasoning = False

        async with client.messages.stream(**request_params) as stream:
            async for event in stream:
                event_type = event.type

                if event_type == "content_block_start":
                    block = event.content_block
                    block_type = block.type

                    if block_type == "thinking":
                        if not is_reasoning:
                            rich.print(
                                f"\n\n[bold green]{'=' * 21} REASONING {'=' * 21}[/bold green]\n\n"
                            )
                            is_reasoning = True

                    elif block_type == "redacted_thinking":
                        # Redacted thinking blocks contain encrypted content
                        if not is_reasoning:
                            rich.print(
                                f"\n\n[bold green]{'=' * 21} REASONING {'=' * 21}[/bold green]\n\n"
                            )
                            is_reasoning = True
                        rich.print("[redacted thinking]", flush=True)

                    elif block_type == "server_tool_use":
                        if not is_searching:
                            rich.print(
                                f"\n\n[bold yellow]{'=' * 21} WEB SEARCH {'=' * 21}[/bold yellow]\n\n"
                            )
                            is_searching = True

                    elif block_type == "text":
                        if not is_response:
                            rich.print(
                                f"\n\n[bold blue]{'=' * 21} RESPONSE {'=' * 21}[/bold blue]\n\n"
                            )
                            is_response = True

                elif event_type == "content_block_delta":
                    delta = event.delta
                    delta_type = delta.type

                    if delta_type == "thinking_delta":
                        print(delta.thinking, end="", flush=True)
                    elif delta_type == "text_delta":
                        print(delta.text, end="", flush=True)

            # Get the final message with full content
            final_message = await stream.get_final_message()

        # Build assistant message from content blocks for multi-turn conversations
        # This preserves thinking blocks, tool_use, text, etc. in Anthropic format
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": [block.model_dump() for block in final_message.content],
        }

        # Process the final message to get complete data
        tool_calls: list[AgentToolCall] = []
        text_chunks: list[str] = []
        thinking_blocks: list[
            dict[str, Any]
        ] = []  # Full blocks with signature for multi-turn
        all_citations: list[dict[str, Any]] = []
        web_search_results: dict[str, list[dict[str, Any]]] = {}

        for block in final_message.content:
            block_type = block.type

            if block_type == "thinking":
                # Capture full thinking block (including signature) for multi-turn support
                thinking_blocks.append(
                    {
                        "type": "thinking",
                        "thinking": getattr(block, "thinking", ""),
                        "signature": getattr(block, "signature", ""),
                    }
                )

            elif block_type == "redacted_thinking":
                # Capture redacted thinking blocks - these contain encrypted content
                # that must be passed back unmodified for multi-turn conversations
                thinking_blocks.append(
                    {
                        "type": "redacted_thinking",
                        "data": getattr(block, "data", ""),
                    }
                )

            elif block_type == "server_tool_use":
                tool_calls.append(
                    AgentToolCall(
                        tool_name="web_search_call",
                        tool_args={
                            "query": block.input.get("query", ""),
                            "status": "completed",
                        },
                        tool_call_id=block.id,
                        completion=assistant_message,
                    )
                )

            elif block_type == "web_search_tool_result":
                results = []
                for result in block.content:
                    if hasattr(result, "url"):
                        results.append(
                            {
                                "url": result.url,
                                "title": getattr(result, "title", ""),
                                "page_age": getattr(result, "page_age", None),
                            }
                        )
                web_search_results[block.tool_use_id] = results

            elif block_type == "text":
                text_chunks.append(block.text)
                if hasattr(block, "citations") and block.citations:
                    for citation in block.citations:
                        all_citations.append(
                            {
                                "url": getattr(citation, "url", ""),
                                "title": getattr(citation, "title", ""),
                                "cited_text": getattr(citation, "cited_text", ""),
                            }
                        )

            elif block_type == "tool_use":
                tool_calls.append(
                    AgentToolCall(
                        tool_name=block.name,
                        tool_args=block.input,
                        tool_call_id=block.id,
                        completion=assistant_message,
                    )
                )

        # Update tool calls with their results
        for tc in tool_calls:
            if (
                tc.tool_name == "web_search_call"
                and tc.tool_call_id in web_search_results
            ):
                tc.tool_args["results"] = web_search_results[tc.tool_call_id]

        # Add citations to the response if present
        if all_citations:
            for tc in tool_calls:
                if tc.tool_name == "web_search_call":
                    tc.tool_args["citations"] = all_citations
                    break

        # Add thinking/reasoning content if present
        # Extract text content from thinking blocks (for display), excluding redacted blocks
        thinking_content = "".join(
            b.get("thinking", "")
            for b in thinking_blocks
            if b.get("type") == "thinking"
        )
        if thinking_content or thinking_blocks:
            # Add to the first tool call (usually web_search_call or text_output)
            if tool_calls:
                if thinking_content:
                    tool_calls[0].tool_args["reasoning"] = thinking_content
                # Store full thinking blocks for multi-turn conversations with tool use
                # These must be passed back unmodified to maintain reasoning continuity
                if thinking_blocks:
                    tool_calls[0].tool_args["thinking_blocks"] = thinking_blocks

        content = "".join(text_chunks)

        # If no tool calls, add text_output
        if len(tool_calls) == 0:
            tool_args: dict[str, Any] = {"content": content}
            if thinking_content:
                tool_args["reasoning"] = thinking_content
            if thinking_blocks:
                tool_args["thinking_blocks"] = thinking_blocks
            tool_calls.append(
                AgentToolCall(
                    tool_name="text_output",
                    tool_args=tool_args,
                    tool_call_id="",
                    completion=assistant_message,
                )
            )

        return content, tool_calls

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
            include: list[str] = ["code_interpreter_call.outputs"]
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
        builtin_tool_calls: list[dict[str, Any]] = []
        message_chunks: list[str] = []

        for output in res.output:
            if isinstance(output, dict):
                if output["type"] == "function_call":
                    tool_calls.append(output)  # type: ignore
                elif output["type"] == "message":
                    message_chunks.append(output["content"][0]["text"])
                elif output["type"] in ("web_search_call", "code_interpreter_call"):
                    builtin_tool_calls.append(output)
            elif output.type == "function_call":
                tool_calls.append(output)  # type: ignore
            elif output.type == "message":
                message_chunks.append(output.content[0].text)  # type: ignore
            elif output.type in ("web_search_call", "code_interpreter_call"):
                builtin_tool_calls.append(
                    output.model_dump()
                    if hasattr(output, "model_dump")
                    else dict(output)
                )

        agent_tool_calls: list[AgentToolCall] = []
        res_dict = res.model_dump()
        outputs = res_dict["output"]

        if len(tool_calls) > 0 or len(builtin_tool_calls) > 0:
            # Build assistant.tool_calls and AgentToolCall objects with consistent ids
            for tc in tool_calls:
                assert tc is not None
                # Handle both dict and object formats
                if isinstance(tc, dict):
                    call_id = tc["call_id"]
                    name = tc["name"]
                    arguments = tc["arguments"]
                else:
                    call_id = tc.call_id
                    name = tc.name
                    arguments = tc.arguments
                assert call_id is not None
                assert name is not None
                assert arguments is not None
                agent_tool_calls.append(
                    AgentToolCall(
                        tool_name=name,
                        tool_args=ujson.loads(arguments),
                        tool_call_id=call_id,
                        # Store the assistant message (with tool_calls) as the completion
                        # so the runtime can append a valid chat message to history.
                        responses=outputs,
                    )
                )

            # Process built-in tool calls (web_search, code_interpreter)
            # These are already executed by OpenAI, so we just capture them for tracing
            for btc in builtin_tool_calls:
                btc_type = btc.get("type", "unknown_builtin")
                btc_id = btc.get("id", "")

                if btc_type == "web_search_call":
                    action = btc.get("action", {})
                    tool_args = {
                        "query": action.get("query", ""),
                        "search_type": action.get("type", ""),
                        "status": btc.get("status", ""),
                    }
                elif btc_type == "code_interpreter_call":
                    tool_args = {
                        "code": btc.get("code", ""),
                        "outputs": btc.get("outputs"),
                        "status": btc.get("status", ""),
                    }
                else:
                    tool_args = btc

                agent_tool_calls.append(
                    AgentToolCall(
                        tool_name=btc_type,
                        tool_args=tool_args,
                        tool_call_id=btc_id,
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
                    item_type = (
                        event.item.get("type")
                        if isinstance(event.item, dict)
                        else getattr(event.item, "type", None)
                    )
                    if item_type == "message":
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
