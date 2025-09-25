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


class ActionCore:
    """
    A bare-bones action structure.
    Contains only the action function and essential metadata.
    """

    def __init__(
        self,
        function: ActionFunction,
        name: str,
        parameters: dict[str, Any],
    ):
        self.name = name
        self.parameters = parameters
        self.function = function

    async def execute(
        self,
        call: AgentToolCall,
        actions: dict[str, "ActionCore"] | None = None,
        action_override: ActionOverrideFunction | None = None,
    ) -> dict[str, str]:
        """
        Execute an action tool and return the response within a MAIL runtime.
        """
        if actions:
            action = actions.get(self.name)
            if action:
                return await action.execute(call, action_override=action_override)

        if not action_override:
            try:
                content = await self.function(call.tool_args)
                return call.create_response_msg(content)
            except Exception as e:
                return call.create_response_msg(f"Error executing action tool: {e}")
        else:
            try:
                response = await action_override(call.tool_args)
                if isinstance(response, str):
                    return call.create_response_msg(response)
                return response
            except Exception as e:
                return call.create_response_msg(
                    f"Error executing action override tool: {e}"
                )
