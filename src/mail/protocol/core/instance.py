# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel

MAILInstanceType = Literal["admin", "user", "swarm"]


def validate_instance_client_id(instance_client_id: str) -> str:
    """
    Validate a MAIL instance client ID.
    """
    if not instance_client_id.strip():
        raise ValueError(f"Invalid MAIL instance client ID: {instance_client_id}")
    return instance_client_id


def validate_swarm_name(swarm_name: str) -> str:
    """
    Validate a MAIL swarm name.
    """
    if not swarm_name.strip():
        raise ValueError(f"Invalid MAIL swarm name: {swarm_name}")
    return swarm_name


class MAILInstance(BaseModel):
    """
    A MAIL instance.
    """
    instance_type: MAILInstanceType
    instance_client_id: Annotated[str, AfterValidator(validate_instance_client_id)]
    swarm_name: Annotated[str, AfterValidator(validate_swarm_name)]