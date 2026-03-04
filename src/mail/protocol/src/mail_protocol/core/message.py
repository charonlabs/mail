# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.address import MAILAddress

MAILMessageType = Literal["direct", "broadcast", "interrupt", "task_complete"]


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


class MAILMessage(BaseModel):
    """
    A MAIL message.
    """
    id: Annotated[str, AfterValidator(validate_uuid4)]
    timestamp: Annotated[str, AfterValidator(validate_timestamp)]
    msg_type: MAILMessageType
    sender: MAILAddress
    recipients: list[MAILAddress]
    subject: str
    body: str
    task_id: Annotated[str, AfterValidator(validate_uuid4)]
    metadata: dict[str, Any]