# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
import os
from collections.abc import Awaitable
from typing import Any, Literal
from uuid import uuid4

import openai
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallUnion,
    ChatCompletionToolUnionParam,
)
from openai.types.responses import ResponseInputParam, ToolParam

from mail.core.agents import AgentOutput
from mail.core.tools import AgentToolCall
from mail.factories.base import MAILAgentFunction
from mail.factories.supervisor import SupervisorFunction


class OpenAIChatCompletionsAgentFunction(MAILAgentFunction):
    """
    A MAIL agent function that uses the OpenAI API to generate chat completions.
    """

    def __init__(
        self,
        name: str,
        comm_targets: list[str],
        model: str,
        tools: list[dict[str, Any]],
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        can_complete_tasks: bool = False,
        tool_format: Literal[
            "completions", "responses"
        ] = "completions",  # kept for compatibility
        exclude_tools: list[str] = [],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            comm_targets=comm_targets,
            tools=tools,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            can_complete_tasks=can_complete_tasks,
            tool_format="completions",
            exclude_tools=exclude_tools,
            **kwargs,
        )
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Generate a chat completion using the OpenAI API.
        """
        return self._run_chat_completion(messages, tool_choice)

    async def _run_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Run a chat completion using the OpenAI API.
        """
        response = await self.client.chat.completions.create(  # type: ignore
            model=self.model,
            messages=self._preprocess_messages(messages),
            tool_choice=tool_choice,
            tools=self._preprocess_tools(),
        )
        choice = response.choices[0]
        message = choice.message
        tool_calls = self._postprocess_tool_calls(message)
        return message.content or None, tool_calls

    def _preprocess_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[ChatCompletionMessageParam]:
        """
        Preprocess the messages for the OpenAI API.
        """
        normalized: list[ChatCompletionMessageParam] = []
        for message in messages:
            entry: dict[str, Any] = {
                "role": message.get("role"),
                "content": message.get("content"),
            }
            if "name" in message:
                entry["name"] = message["name"]
            if "tool_calls" in message:
                entry["tool_calls"] = message["tool_calls"]
            if "tool_call_id" in message:
                entry["tool_call_id"] = message["tool_call_id"]
            normalized.append(entry)  # type: ignore[arg-type]
        return normalized

    def _preprocess_tools(self) -> list[ChatCompletionToolUnionParam]:
        """
        Preprocess the tools for the OpenAI API.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in self.tools
        ]

    def _postprocess_tool_calls(
        self,
        message: Any,
    ) -> list[AgentToolCall]:
        """
        Postprocess the tool calls from the OpenAI API response.
        """
        tool_calls: list[ChatCompletionMessageToolCallUnion] = list(
            getattr(message, "tool_calls", []) or []
        )
        if not tool_calls:
            return []

        message_dict = message.model_dump(exclude_none=False)
        call_records: list[tuple[str, str, str, dict[str, Any]]] = []

        for tool_call in tool_calls:
            call_id = getattr(tool_call, "id", None) or f"call_{uuid4()}"
            function_call = getattr(tool_call, "function", None)
            custom_call = getattr(tool_call, "custom", None)
            name = None
            raw_args = "{}"
            if function_call is not None:
                name = getattr(function_call, "name", None)
                raw_args = getattr(function_call, "arguments", "{}") or "{}"
            elif custom_call is not None:
                name = getattr(custom_call, "name", None)
                raw_args = getattr(custom_call, "input", "{}") or "{}"

            if not name:
                continue

            try:
                parsed_args = json.loads(raw_args)
            except json.JSONDecodeError:
                parsed_args = {"raw": raw_args}

            call_records.append((call_id, name, raw_args, parsed_args))

        patched_calls: list[dict[str, Any]] = []
        for call_id, name, raw_args, parsed_args in call_records:
            patched_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": raw_args,
                    },
                }
            )

        message_dict["tool_calls"] = patched_calls

        agent_calls: list[AgentToolCall] = []
        for call_id, name, raw_args, parsed_args in call_records:
            agent_calls.append(
                AgentToolCall(
                    tool_name=name,
                    tool_args=parsed_args,
                    tool_call_id=call_id,
                    completion=message_dict,
                )
            )

        return agent_calls


class OpenAIChatCompletionsSupervisorFunction(SupervisorFunction):
    """
    A MAIL supervisor function that uses the OpenAI API to generate chat completions.
    """

    def __init__(
        self,
        name: str,
        comm_targets: list[str],
        model: str,
        tools: list[dict[str, Any]],
        can_complete_tasks: bool = True,
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
        exclude_tools: list[str] = [],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            comm_targets=comm_targets,
            tools=tools,
            can_complete_tasks=True,  # supervisor can always complete tasks; param kept for compatibility
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            tool_format="completions",
            exclude_tools=exclude_tools,
            **kwargs,
        )
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.supervisor_fn = OpenAIChatCompletionsAgentFunction(
            name=name,
            comm_targets=comm_targets,
            model=model,
            tools=self.tools,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            can_complete_tasks=True,  # supervisor can always complete tasks; param kept for compatibility
            tool_format="completions",
            exclude_tools=exclude_tools,
            **kwargs,
        )

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Generate a chat completion using the OpenAI API.
        """
        return self.supervisor_fn(messages, tool_choice)


class OpenAIResponsesAgentFunction(MAILAgentFunction):
    """
    A MAIL agent function that uses the OpenAI API to generate responses.
    """

    def __init__(
        self,
        name: str,
        comm_targets: list[str],
        model: str,
        tools: list[dict[str, Any]],
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        can_complete_tasks: bool = False,
        tool_format: Literal[
            "completions", "responses"
        ] = "responses",  # kept for compatibility
        exclude_tools: list[str] = [],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            comm_targets=comm_targets,
            tools=tools,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            can_complete_tasks=can_complete_tasks,
            tool_format="responses",
            exclude_tools=exclude_tools,
            **kwargs,
        )
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Generate a response using the OpenAI API.
        """
        return self._run_response(messages, tool_choice)

    async def _run_response(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> AgentOutput:
        """
        Run a response using the OpenAI API.
        """
        response = await self.client.responses.create(  # type: ignore
            model=self.model,
            input=self._preprocess_messages(messages),
            tool_choice=tool_choice,
            tools=self._preprocess_tools(),
        )
        response_dict = response.model_dump()
        outputs: list[dict[str, Any]] = response_dict.get("output", [])
        # Deep-copy outputs so we can normalise in place without mutating original objects
        normalized_outputs: list[dict[str, Any]] = json.loads(json.dumps(outputs))
        text_segments: list[str] = []
        call_records: list[tuple[str, str, dict[str, Any]]] = []

        for block in outputs:
            block_type = block.get("type")
            if block_type == "message":
                for content in block.get("content", []):
                    if content.get("type") in {"output_text", "text"}:
                        text_segments.append(content.get("text", ""))
            elif block_type in {"custom_tool_call", "tool_call", "function_call"}:
                name = (
                    block.get("name")
                    or block.get("tool", {}).get("name")
                    or block.get("function", {}).get("name")
                )
                if not name:
                    continue
                call_id = block.get("call_id") or block.get("id") or f"call_{uuid4()}"
                raw_input = (
                    block.get("input")
                    or block.get("tool_input")
                    or block.get("arguments")
                    or "{}"
                )
                if isinstance(raw_input, dict):
                    parsed_input = raw_input
                else:
                    try:
                        parsed_input = json.loads(raw_input)
                    except json.JSONDecodeError:
                        parsed_input = {"raw": raw_input}
                call_records.append((call_id, name, parsed_input))

        for block in normalized_outputs:
            if block.get("type") == "message":
                for content in block.get("content", []):
                    if content.get("type") == "output_text":
                        content["type"] = "text"

        agent_tool_calls = [
            AgentToolCall(
                tool_name=name,
                tool_args=tool_args,
                tool_call_id=call_id,
                responses=normalized_outputs,
            )
            for call_id, name, tool_args in call_records
        ]

        response_text = "\n".join(filter(None, text_segments)) or None
        return response_text, agent_tool_calls

    def _preprocess_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[ResponseInputParam]:
        """
        Preprocess the messages for the OpenAI API.
        """
        normalized: list[ResponseInputParam] = []
        for message in messages:
            entry: dict[str, Any] = {
                "role": message.get("role"),
                "content": message.get("content"),
            }
            if "name" in message:
                entry["name"] = message["name"]
            if "tool_call_id" in message:
                entry["tool_call_id"] = message["tool_call_id"]
            normalized.append(entry)  # type: ignore[arg-type]
        return normalized

    def _preprocess_tools(self) -> list[ToolParam]:
        """
        Preprocess the tools for the OpenAI API.
        """
        return [
            {  # type: ignore
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description"),
                    "parameters": tool.get("parameters"),
                },
            }
            for tool in self.tools
        ]


class OpenAIResponsesSupervisorFunction(SupervisorFunction):
    """
    A MAIL supervisor function that uses the OpenAI API to generate responses.
    """

    def __init__(
        self,
        name: str,
        comm_targets: list[str],
        model: str,
        tools: list[dict[str, Any]],
        can_complete_tasks: bool = True,
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
        exclude_tools: list[str] = [],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            comm_targets=comm_targets,
            tools=tools,
            can_complete_tasks=True,  # supervisor can always complete tasks; param kept for compatibility
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            tool_format="responses",
            exclude_tools=exclude_tools,
            **kwargs,
        )
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.supervisor_fn = OpenAIResponsesAgentFunction(
            name=name,
            comm_targets=comm_targets,
            model=model,
            tools=self.tools,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            can_complete_tasks=True,  # supervisor can always complete tasks; param kept for compatibility
            tool_format="responses",
            exclude_tools=exclude_tools,
            **kwargs,
        )

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[AgentOutput]:
        """
        Generate a response using the OpenAI API.
        """
        return self.supervisor_fn(messages, tool_choice)
