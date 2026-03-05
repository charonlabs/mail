# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.message import MAILMessage
from mail_protocol.core.swarm import MAILSwarm
from mail_protocol.interswarm import MAILRemoteSwarm
from mail_protocol.metadata import Metadata


def validate_uptime(uptime: float) -> float:
    """
    Validate the uptime (must be a positive number).
    """
    if uptime < 0:
        raise ValueError(f"Invalid uptime: {uptime}")
    return uptime


class GetRootResponse(BaseModel):
    """
    A response body to the endpoint `GET /`.
    """
    protocol_name: Literal["mail"]
    protocol_version: Literal["2.0"]
    status: Literal["running"]
    uptime: Annotated[float, AfterValidator(validate_uptime)]
    metadata: Metadata


class GetSwarmResponse(BaseModel):
    """
    A response body to the endpoint `GET /swarm`.
    """
    swarm: MAILSwarm
    protocol_version: str
    status: Literal["running"]
    metadata: Metadata


class GetRegistryResponse(BaseModel):
    """
    A response body to the endpoint `GET /registry`.
    """
    swarms: dict[str, MAILRemoteSwarm]
    metadata: Metadata


class PostRegistryResponse(BaseModel):
    """
    A response body to the endpoint `POST /registry`.
    """
    status: Literal["success", "error"]
    swarm: MAILRemoteSwarm
    metadata: Metadata


class PostMessageResponse(BaseModel):
    """
    A response body to the endpoint `POST /message`.
    """
    message: MAILMessage
    metadata: Metadata


class PostInterswarmMessageResponse(BaseModel):
    """
    A response body to the endpoint `POST /interswarm/message`.
    """
    status: Literal["success", "error"]
    new_task: bool
    metadata: Metadata