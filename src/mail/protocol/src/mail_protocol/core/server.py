# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

from pydantic import BaseModel


class MAILServerSentEvent(BaseModel):
    """
    A MAIL server-sent event (SSE).
    """
    event: str
    data: dict[str, Any]