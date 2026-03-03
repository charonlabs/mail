# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

from pydantic import BaseModel

from mail.protocol.core.message import MAILMessage
from mail.protocol.interswarm.attachment import MAILInterswarmAttachment
from mail.protocol.interswarm.task import MAILInterswarmTask


class MAILInterswarmMessage(BaseModel):
    """
    A MAIL interswarm message.
    """
    interswarm_message_id: str
    source_swarm: str
    target_swarm: str
    timestamp: str
    payload: MAILMessage
    task: MAILInterswarmTask
    attachments: list[MAILInterswarmAttachment]
    metadata: dict[str, Any]