# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any, Literal, TypedDict


class AgentHistoriesDB(TypedDict):
    """
    A database for storing agent histories.
    """
    id: str
    swarm_name: str
    caller_role: Literal["admin", "agent", "user"]
    caller_id: str
    tool_format: Literal["completions", "responses"]
    task_id: str
    agent_name: str
    history: list[dict[str, Any]]


