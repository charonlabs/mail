from collections.abc import Awaitable, Callable
import logging
from typing import Any, Literal
from uuid import uuid4

import ujson
from langmem import create_memory_store_manager
from langsmith import traceable
from litellm import OutputFunctionToolCall, OutputText, ResponsesAPIResponse, acompletion, aresponses, ResponseOutputItem
from openai.types.responses.response_output_message import ResponseOutputMessage
from pydantic import BaseModel

from mail.tools import AgentToolCall, create_mail_tools

from ..store import get_langmem_store

AgentFunction = Callable[
    [list[dict[str, Any]], str], Awaitable[tuple[str | None, list[AgentToolCall]]]
]

logger = logging.getLogger("mail")

def base_agent_factory(
    user_token: str,
    llm: str,
    comm_targets: list[str],
    agent_params: dict[str, Any],
    tools: list[dict[str, Any]],
    system: str,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    name: str = "base_agent",
) -> AgentFunction:
    if not llm.startswith("litellm_proxy/"):
        llm = f"litellm_proxy/{llm}"

    thinking: dict[str, Any] = {
        "type": "disabled",
    }

    if reasoning_effort is not None:
        if thinking_budget is None:
            if reasoning_effort == "low":
                thinking_budget = 1024
            elif reasoning_effort == "medium":
                thinking_budget = 2048
            elif reasoning_effort == "high":
                thinking_budget = 4096

    if thinking_budget is not None:
        if max_tokens is None:
            max_tokens = thinking_budget + 4000
        thinking = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }

    @traceable(name=name)
    async def run(
        messages: list[dict[str, Any]], tool_choice: str = "required"
    ) -> tuple[str | None, list[AgentToolCall]]:
        if not messages[0]["role"] == "system":
            messages.insert(0, {"role": "system", "content": system})

        if memory:
            async with get_langmem_store() as store:
                manager = create_memory_store_manager(
                    "anthropic:claude-sonnet-4-20250514",
                    query_model="anthropic:claude-sonnet-4-20250514",
                    query_limit=10,
                    namespace=(f"{name}_memory",),
                    store=store,
                )
                memories = await manager.asearch(
                    query=f"{messages[-1]['content']}", limit=10
                )
                memories_str = ""
                for i, mem in enumerate(memories):
                    memories_str += f"[{i + 1}]\n{mem.value.content}\n\n"
                messages[-1]["content"] += (
                    f"\n\n<internal_memories>\n{memories_str.strip()}\n</internal_memories>"
                )

        # add the agent's tools to the list of tools
        enable_interswarm = agent_params.get("enable_interswarm", False)
        agent_tools = create_mail_tools(comm_targets, enable_interswarm) + tools
        for tool in agent_tools:
            frozen_tool = tool.copy()
            tool["function"] = frozen_tool
            tool["type"] = "function"

        res = await acompletion(
            model=llm,
            messages=messages,
            tools=agent_tools,
            thinking=thinking,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            tool_choice=tool_choice,
            extra_headers={"Authorization": f"Bearer {user_token}"},
        )

        msg = res.choices[0].message
        tool_calls = []
        if msg.content:
            pass
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_calls.append(
                    AgentToolCall(
                        tool_name=tool_call.function.name,
                        tool_args=ujson.loads(tool_call.function.arguments),
                        tool_call_id=tool_call.id or f"call_{uuid4()}",
                        completion=res.choices[0].message.to_dict(),
                    )
                )

        if memory:
            async with get_langmem_store() as store:
                manager = create_memory_store_manager(
                    "anthropic:claude-sonnet-4-20250514",
                    query_model="anthropic:claude-sonnet-4-20250514",
                    query_limit=10,
                    namespace=(f"{name}_memory",),
                    store=store,
                )

                tool_call_str = ""
                for call in tool_calls:
                    tool_call_str += f"<tool_call>\n<tool_name>{call.tool_name}</tool_name>\n<tool_args>{ujson.dumps(call.tool_args)}</tool_args>\n</tool_call>\n\n"

                assistant_msg = f"{tool_call_str.strip()}\n\n<assistant_response>\n{msg.content}\n</assistant_response>"

                await manager.ainvoke(
                    {
                        "messages": [
                            {"role": "user", "content": messages[-1]["content"]},
                            {"role": "assistant", "content": assistant_msg},
                        ]
                    }
                )

        return msg.content, tool_calls

    return run

def base_agent_factory_with_responses(
    user_token: str,
    llm: str,
    comm_targets: list[str],
    agent_params: dict[str, Any],
    tools: list[dict[str, Any]],
    system: str,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    name: str = "base_agent",
) -> AgentFunction:
    if not llm.startswith("litellm_proxy/"):
        llm = f"litellm_proxy/{llm}"

    if reasoning_effort is not None:
        if thinking_budget is None:
            if reasoning_effort == "low":
                thinking_budget = 1024
            elif reasoning_effort == "medium":
                thinking_budget = 2048
            elif reasoning_effort == "high":
                thinking_budget = 4096

    @traceable(name=name)
    async def run(
        messages: list[dict[str, Any]], tool_choice: str = "required"
    ) -> tuple[str | None, list[AgentToolCall]]:
        if not messages[0]["role"] == "system":
            messages.insert(0, {"role": "system", "content": system})

        if memory:
            async with get_langmem_store() as store:
                manager = create_memory_store_manager(
                    "anthropic:claude-sonnet-4-20250514",
                    query_model="anthropic:claude-sonnet-4-20250514",
                    query_limit=10,
                    namespace=(f"{name}_memory",),
                    store=store,
                )
                memories = await manager.asearch(
                    query=f"{messages[-1]['content']}", limit=10
                )
                memories_str = ""
                for i, mem in enumerate(memories):
                    memories_str += f"[{i + 1}]\n{mem.value.content}\n\n"
                messages[-1]["content"] += (
                    f"\n\n<internal_memories>\n{memories_str.strip()}\n</internal_memories>"
                )

        # add the agent's tools to the list of tools
        enable_interswarm = agent_params.get("enable_interswarm", False)
        agent_tools = create_mail_tools(comm_targets, enable_interswarm) + tools

        res = await aresponses(
            input=messages,
            model=llm,
            max_output_tokens=max_tokens,
            reasoning={
                "effort": reasoning_effort,
                "summary": "auto",
            },
            tool_choice=tool_choice,
            tools=agent_tools,
            extra_headers={"Authorization": f"Bearer {user_token}"},
        )

        output_messages: list[ResponseOutputMessage | None] = [output if output.type == "message" else None for output in res.output]
        output_messages = [msg for msg in output_messages if msg is not None]

        assert len(output_messages) == 1, f"expected 1 output message, got {len(output_messages)}"
        output_message = output_messages[0]
        assert output_message is not None

        if output_message.content[0].type == "output_text":
            output_text = output_message.content[0].text or ""
        elif output_message.content[0].type == "refusal":
            output_text = output_message.content[0].refusal or ""
        else:
            raise ValueError(f"unexpected output type: {output_message.content[0].type}")

        tool_calls: list[OutputFunctionToolCall | None] = [output if output.type == "function_call" else None for output in res.output]
        tool_calls = [tool_call for tool_call in tool_calls if tool_call is not None]
        assert len(tool_calls) > 0, f"expected at least 1 tool call, got {len(tool_calls)}"

        agent_tool_calls = []
        for tool_call in tool_calls:
            assert tool_call is not None
            assert tool_call.type == "function_call"
            agent_tool_calls.append(
                AgentToolCall(
                    tool_name=tool_call.name or "",
                    tool_args=ujson.loads(tool_call.arguments or ""),
                    tool_call_id=tool_call.id or f"call_{uuid4()}",
                    completion=tool_call.model_dump() or {},
                )
            )

        if memory:
            async with get_langmem_store() as store:
                manager = create_memory_store_manager(
                    "anthropic:claude-sonnet-4-20250514",
                    query_model="anthropic:claude-sonnet-4-20250514",
                    query_limit=10,
                    namespace=(f"{name}_memory",),
                    store=store,
                )

                tool_call_str = ""
                for call in agent_tool_calls:
                    tool_call_str += f"<tool_call>\n<tool_name>{call.tool_name}</tool_name>\n<tool_args>{ujson.dumps(call.tool_args)}</tool_args>\n</tool_call>\n\n"

                assistant_msg = f"{tool_call_str.strip()}\n\n<assistant_response>\n{output_text}\n</assistant_response>"

                await manager.ainvoke(
                    {
                        "messages": [
                            {"role": "user", "content": messages[-1]["content"]},
                            {"role": "assistant", "content": assistant_msg},
                        ]
                    }
                )

        return output_text, agent_tool_calls

    return run