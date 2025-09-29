# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


def _client_defaults() -> dict[str, Any]:
    """
    Get the default client config.
    """
    return {
        "timeout": 3600.0,
    }


class ClientConfig(BaseModel):
    timeout: float = Field(default_factory=lambda: _client_defaults()["timeout"])