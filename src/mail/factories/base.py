import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from uuid import uuid4

import langsmith as ls
import ujson
from langmem import create_memory_store_manager
from litellm import (
    OutputFunctionToolCall,
    acompletion,
    aresponses,
)

from mail.tools import AgentToolCall, create_mail_tools

AgentFunction = Callable[
    [list[dict[str, Any]], str], Awaitable[tuple[str | None, list[AgentToolCall]]]
]

logger = logging.getLogger("mail")


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
    # instance params
    # ...
    # internal params
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    use_proxy: bool = True,
    inference_api: Literal["completions", "responses"] = "completions",
    _debug_include_mail_tools: bool = True,
) -> AgentFunction:
    extra_headers: dict[str, str] = {}
    if use_proxy:
        if not llm.startswith("litellm_proxy/"):
            llm = f"litellm_proxy/{llm}"
        extra_headers["Authorization"] = f"Bearer {user_token}"

    thinking: dict[str, Any] = {
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
        thinking = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }

    def preprocess(
        messages: list[dict[str, Any]], style: Literal["completions", "responses"]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not messages[0]["role"] == "system" and not system == "":
            messages.insert(0, {"role": "system", "content": system})

        # add the agent's tools to the list of tools
        if _debug_include_mail_tools:
            agent_tools = (
                create_mail_tools(comm_targets, enable_interswarm, style=style) + tools
            )
        else:
            agent_tools = tools
        return messages, agent_tools

    if inference_api == "completions":

        async def run_completions(
            messages: list[dict[str, Any]], tool_choice: str = "required"
        ) -> tuple[str | None, list[AgentToolCall]]:
            messages, agent_tools = preprocess(messages, "completions")

            with ls.trace(
                name=f"{name}_completions",
                run_type="llm",
                inputs={
                    "messages": messages,
                    "tools": agent_tools,
                    "thinking": thinking,
                    "reasoning_effort": reasoning_effort,
                    "max_tokens": max_tokens,
                    "tool_choice": tool_choice,
                },
            ) as rt:
                res = await acompletion(
                    model=llm,
                    messages=messages,
                    tools=agent_tools,
                    thinking=thinking,
                    reasoning_effort=reasoning_effort,
                    max_tokens=max_tokens,
                    tool_choice=tool_choice,
                    extra_headers=extra_headers,
                )
                rt.end(outputs={"output": res})

            msg = res.choices[0].message
            tool_calls: list[AgentToolCall] = []
            # Normalize assistant message to a dict so we can ensure consistent tool_call ids
            assistant_dict = msg.to_dict()
            # Prepare patched tool_calls list for assistant message
            assistant_tool_calls: list[dict[str, Any]] = []
            if getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    call_id = tc.id or f"call_{uuid4()}"
                    # Patch assistant tool_calls with consistent id
                    assistant_tool_calls.append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                    )
                    tool_calls.append(
                        AgentToolCall(
                            tool_name=tc.function.name,
                            tool_args=ujson.loads(tc.function.arguments),
                            tool_call_id=call_id,
                            completion=assistant_dict,
                        )
                    )
            # If there were tool calls, ensure the assistant message reflects the ids we used
            if assistant_tool_calls:
                assistant_dict["tool_calls"] = assistant_tool_calls

            return msg.content, tool_calls

        return run_completions

    async def run_responses(
        messages: list[dict[str, Any]], tool_choice: str = "required"
    ) -> tuple[str | None, list[AgentToolCall]]:
        messages, agent_tools = preprocess(messages, "responses")
        print("agent_tools", agent_tools)

        with ls.trace(
            name=f"{name}_responses",
            run_type="llm",
            inputs={
                "messages": messages,
                "tools": agent_tools,
                "thinking": thinking,
                "reasoning_effort": reasoning_effort,
                "max_tokens": max_tokens,
                "tool_choice": tool_choice,
            },
        ) as rt:
            res = await aresponses(
                input=messages,
                model=llm,
                max_output_tokens=max_tokens,
                include=["reasoning.encrypted_content"],
                reasoning={
                    "effort": reasoning_effort,
                    "summary": "auto",
                },
                tool_choice=tool_choice,
                tools=agent_tools,
                extra_headers=extra_headers,
            )
            rt.end(outputs={"output": res})

        tool_calls: list[OutputFunctionToolCall | None] = [
            output if output.type == "function_call" else None for output in res.output
        ]
        tool_calls = [tool_call for tool_call in tool_calls if tool_call is not None]

        agent_tool_calls: list[AgentToolCall] = []
        res_dict = res.model_dump()
        outputs = res_dict["output"]
        if len(tool_calls) > 0:
            # Build assistant.tool_calls and AgentToolCall objects with consistent ids
            for tc in tool_calls:
                assert tc is not None
                assert tc.id is not None
                assert tc.name is not None
                assert tc.arguments is not None
                call_id = tc.id
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

    return run_responses
