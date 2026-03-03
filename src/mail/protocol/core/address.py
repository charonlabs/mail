# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel


def validate_address(address: str) -> str:
    """
    Validate a MAIL-compliant address.
    """
    if "@" in address:
        agent_name, swarm_name = address.split("@", 1)
        if not agent_name.strip() or not swarm_name.strip():
            raise ValueError(f"Invalid MAIL address: {address}")
        return address
    else:
        if not address.strip():
            raise ValueError(f"Invalid MAIL address: {address}")
        return address


class MAILAddress(BaseModel):
    """
    A MAIL-compliant address for an agent, admin, user, or system.
    """
    addr_type: Literal["admin", "agent", "user", "system"]
    address: Annotated[str, AfterValidator(validate_address)]
