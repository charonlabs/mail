# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Literal

from pydantic import BaseModel


class MAILInstance(BaseModel):
    """
    A MAIL instance.
    """
    instance_type: Literal["admin", "user", "swarm"]
    instance_client_id: str
    swarm_name: str