# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

from pydantic import BaseModel


class MAILRemoteSwarm(BaseModel):
    """
    A MAIL remote swarm.
    """
    name: str
    base_url: str
    protocol_version: str
    active: bool
    last_seen: str | None
    description: str | None
    keywords: list[str] | None
    metadata: dict[str, Any]