# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

from collections.abc import Awaitable, Callable
from typing import Any

from mail.core.tools import AgentToolCall

ActionFunction = Callable[[dict[str, Any]], Awaitable[str]]
"""
A function that executes an action tool and returns the response.
"""

ActionOverrideFunction = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | str]]
"""
A function that overrides an action tool and returns the response.
"""

async def execute_action_tool(
    call: AgentToolCall,
    actions: dict[str, ActionFunction],
    action_override: ActionOverrideFunction | None = None,
) -> dict[str, str]:
    """
    Execute an action tool and return the response within a MAIL runtime.
    """
    if not action_override:
        action = actions[call.tool_name]
        content = await action(call.tool_args)
        return call.create_response_msg(content)
    response = await action_override(call.tool_args)
    if isinstance(response, str):
        return call.create_response_msg(response)
    return response
