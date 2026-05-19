# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MAILSwarm(BaseModel):
    """
    Abstract MAIL swarm class.
    """

    name: str
    description: str
    keywords: list[str]
    agents: list[str]
    metadata: dict[str, Any]


class MAILSwarmSummary(BaseModel):
    """
    More concise summary of a MAIL swarm.
    """

    name: str
    description_abridged: str
    keywords: list[str]
    num_agents: int
