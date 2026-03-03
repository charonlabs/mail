# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Literal

from pydantic import BaseModel


class MAILAddress(BaseModel):
    """
    A MAIL-compliant address for an agent, admin, user, or system.
    """
    addr_type: Literal["admin", "agent", "user", "system"]
    address: str