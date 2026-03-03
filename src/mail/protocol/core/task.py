# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

from pydantic import BaseModel

from mail.protocol.core.address import MAILAddress
from mail.protocol.core.message import MAILMessage


class MAILTask(BaseModel):
    """
    A MAIL task.
    """
    task_id: str
    task_owner: MAILAddress
    task_contributors: list[MAILAddress]
    start_time: str
    completed: bool
    messages: list[MAILMessage]
    metadata: dict[str, Any]