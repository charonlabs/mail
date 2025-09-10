from typing import Awaitable, Callable, Literal, Any, Sequence


from .base import AgentFunction, base_agent_factory
from ..swarms.utils import create_tools_from_actions
from openai.resources.responses.responses import _make_tools
from openai import pydantic_function_tool
from pydantic import BaseModel

ActionFunction = Callable[[dict[str, Any]], Awaitable[str]]
ActionOverrideFunction = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | str]]


def action_agent_factory(
    user_token: str,
    llm: str,
    comm_targets: list[str],
    agent_params: dict[str, Any],
    tools: list[dict[str, Any]] | Sequence[type[BaseModel]],
    system: str,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    memory: bool = True,
    use_proxy: bool = True,
    inference_api: Literal["completions", "responses"] = "responses",
    name: str = "action",
    _debug_include_mail_tools: bool = True,
) -> AgentFunction:
    # ensure that the action tools are in the correct format
    print("tools", tools)
    parsed_tools: list[dict[str, Any]] = []
    if not isinstance(tools[0], dict):
        parsed_tools = [pydantic_function_tool(tool) for tool in tools]  # type: ignore
        if inference_api == "responses":
            parsed_tools = _make_tools(parsed_tools)  # type: ignore

    else:
        parsed_tools = tools  # type: ignore
    print("parsed_tools", parsed_tools)

    agent = base_agent_factory(
        user_token=user_token,
        llm=llm,
        comm_targets=comm_targets,
        agent_params=agent_params,
        tools=parsed_tools,
        system=system,
        reasoning_effort=reasoning_effort,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        memory=memory,
        use_proxy=use_proxy,
        inference_api=inference_api,
        name=name,
        _debug_include_mail_tools=_debug_include_mail_tools,
    )
    return agent
