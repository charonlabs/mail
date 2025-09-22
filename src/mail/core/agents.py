# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from mail.core.tools import AgentToolCall

AgentFunction = Callable[
    [list[dict[str, Any]], str], Awaitable[tuple[str | None, list[AgentToolCall]]]
]
"""
A function that takes a chat history and returns a response and tool calls.
"""

class AgentCore(TypedDict):
    """
    A bare-bones agent structure.
    Contains only the agent function and essential metadata.
    """

    function: AgentFunction
    """The agent function."""
    comm_targets: list[str]
    """The communication targets of the agent."""
    enable_entrypoint: bool
    """Whether the agent can receive messages from users."""
    enable_interswarm: bool
    """Whether the agent can send or receive interswarm messages."""
    can_complete_tasks: bool
    """Whether the agent can complete tasks."""