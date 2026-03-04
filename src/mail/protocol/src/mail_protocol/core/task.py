# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.address import MAILAddress
from mail_protocol.core.message import MAILMessage


def validate_uuid4(uuid4: str) -> str:
    """
    Validate a UUID4 string.
    """
    try:
        uuid.UUID(uuid4)
    except ValueError:
        raise ValueError(f"Invalid UUID4: {uuid4}")
    return uuid4


def validate_timestamp(timestamp: str) -> str:
    """
    Validate a timestamp string.
    """
    try:
        datetime.fromisoformat(timestamp)
    except ValueError:
        raise ValueError(f"Invalid timestamp: {timestamp}")
    return timestamp


class MAILTask(BaseModel):
    """
    A MAIL task.
    """
    task_id: Annotated[str, AfterValidator(validate_uuid4)]
    task_owner: MAILAddress
    task_contributors: list[MAILAddress]
    start_time: Annotated[str, AfterValidator(validate_timestamp)]
    completed: bool
    messages: list[MAILMessage]
    metadata: dict[str, Any]