# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.message import MAILMessage
from mail_protocol.interswarm.attachment import MAILInterswarmAttachment
from mail_protocol.interswarm.task import MAILInterswarmTask


def validate_uuid4(uuid4: str) -> str:
    """
    Validate a UUID4 string.
    """
    try:
        uuid.UUID(uuid4)
    except ValueError:
        raise ValueError(f"Invalid UUID4: {uuid4}")
    return uuid4


def validate_swarm_name(swarm_name: str) -> str:
    """
    Validate a MAIL swarm name.
    """
    if not swarm_name.strip():
        raise ValueError(f"Invalid MAIL swarm name: {swarm_name}")
    return swarm_name


def validate_timestamp(timestamp: str) -> str:
    """
    Validate a timestamp string.
    """
    try:
        datetime.fromisoformat(timestamp)
    except ValueError:
        raise ValueError(f"Invalid timestamp: {timestamp}")
    return timestamp


class MAILInterswarmMessage(BaseModel):
    """
    A MAIL interswarm message.
    """
    interswarm_message_id: Annotated[str, AfterValidator(validate_uuid4)]
    source_swarm: Annotated[str, AfterValidator(validate_swarm_name)]
    target_swarm: Annotated[str, AfterValidator(validate_swarm_name)]
    timestamp: Annotated[str, AfterValidator(validate_timestamp)]
    payload: MAILMessage
    task: MAILInterswarmTask
    attachments: list[MAILInterswarmAttachment]
    metadata: dict[str, Any]