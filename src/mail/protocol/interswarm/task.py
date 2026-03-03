# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

from pydantic import BaseModel

from mail.protocol.core.instance import MAILInstance


class MAILInterswarmTask(BaseModel):
    """
    A MAIL interswarm task.
    """
    task_id: str
    task_owner: MAILInstance
    task_contributors: list[MAILInstance]
    start_time: str
    completed: bool
    metadata: dict[str, Any]