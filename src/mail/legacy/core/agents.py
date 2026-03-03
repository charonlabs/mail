# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

from collections.abc import Awaitable, Callable
from typing import Any

from .actions import ActionCore
from .tools import AgentToolCall

AgentOutput = tuple[str | None, list[AgentToolCall]]
"""
Response type of a MAIL agent containing a response and tool calls.
"""

AgentFunction = Callable[
    [list[dict[str, Any]], str | dict[str, str]],
    Awaitable[AgentOutput],
]
"""
A function that takes a chat history and returns a response and tool calls.
"""


class AgentCore:
    """
    A bare-bones agent structure.
    Contains only the agent function and essential metadata.
    """

    def __init__(
        self,
        function: AgentFunction,
        comm_targets: list[str],
        actions: dict[str, ActionCore] | None = None,
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        can_complete_tasks: bool = False,
    ):
        self.function = function
        self.comm_targets = comm_targets
        if actions is None:
            self.actions = {}
        else:
            self.actions = actions
        self.enable_entrypoint = enable_entrypoint
        self.enable_interswarm = enable_interswarm
        self.can_complete_tasks = can_complete_tasks

    def can_access_action_or_tool(self, name: str) -> bool:
        """
        Check if the agent can access a tool by name.
        """
        match name:
            case (
                "send_request"
                | "send_response"
                | "send_interrupt"
                | "send_broadcast"
                | "acknowledge_broadcast"
                | "ignore_broadcast"
                | "help"
            ):
                return True
            case "task_complete":
                return self.can_complete_tasks
            case _:
                return name in self.actions

    def can_access_action(self, action_name: str) -> bool:
        """
        Check if the agent can access an action by name.
        """
        return action_name in self.actions
