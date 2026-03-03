# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any, Literal

from pydantic import BaseModel

from mail.protocol.core.address import MAILAddress


class MAILMessage(BaseModel):
    """
    A MAIL message.
    """
    id: str
    timestamp: str
    msg_type: Literal["direct", "broadcast", "interrupt", "task_complete"]
    sender: MAILAddress
    recipients: list[MAILAddress]
    subject: str
    body: str
    task_id: str
    metadata: dict[str, Any]