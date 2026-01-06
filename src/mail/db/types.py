# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any, Literal, TypedDict


class AgentHistoriesDB(TypedDict):
    """
    A database record for storing agent histories.
    """

    id: str
    swarm_name: str
    caller_role: Literal["admin", "agent", "user"]
    caller_id: str
    tool_format: Literal["completions", "responses"]
    task_id: str
    agent_name: str
    history: list[dict[str, Any]]


class TaskDB(TypedDict):
    """
    A database record for storing MAILTask metadata.
    """

    id: str
    task_id: str
    swarm_name: str
    caller_role: Literal["admin", "agent", "user"]
    caller_id: str
    task_owner: str
    task_contributors: list[str]
    remote_swarms: list[str]
    is_running: bool
    completed: bool
    start_time: str  # ISO format timestamp


class TaskEventDB(TypedDict):
    """
    A database record for storing task SSE events.
    """

    id: str
    task_id: str
    swarm_name: str
    caller_role: Literal["admin", "agent", "user"]
    caller_id: str
    event_type: str | None
    event_data: str | None
    event_id: str | None


class TaskResponseDB(TypedDict):
    """
    A database record for storing task response messages.
    """

    id: str
    task_id: str
    swarm_name: str
    caller_role: Literal["admin", "agent", "user"]
    caller_id: str
    response: dict[str, Any]
