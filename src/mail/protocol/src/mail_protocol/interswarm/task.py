# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.instance import MAILInstance


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


class MAILInterswarmTask(BaseModel):
    """
    A MAIL interswarm task.
    """
    task_id: Annotated[str, AfterValidator(validate_uuid4)]
    task_owner: MAILInstance
    task_contributors: list[MAILInstance]
    start_time: Annotated[str, AfterValidator(validate_timestamp)]
    completed: bool
    metadata: dict[str, Any]