# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from mail_protocol.core.message import MAILMessage
from mail_protocol.interswarm import MAILRemoteSwarm
from mail_protocol.interswarm.message import MAILInterswarmMessage
from mail_protocol.metadata import Metadata
from mail_protocol.network.responses import PostInterswarmMessageResponse
from pydantic import BaseModel, Field

EndpointFunction = Callable[..., Any]
PostMessageHandler = Callable[[MAILMessage], Awaitable[tuple[MAILMessage, Metadata]]]
PostInterswarmMessageHandler = Callable[
    [MAILInterswarmMessage],
    Awaitable[PostInterswarmMessageResponse],
]
LifecycleHandler = Callable[..., Awaitable[None] | None]


class SwarmRegistryEntry(BaseModel):
    """
    A given entry in the registry of remote swarms.
    """

    swarm: MAILRemoteSwarm
    api_key_ref: str
    public: bool
    volatile: bool


class PersistedSwarmRegistry(BaseModel):
    """
    JSON representation for persisted MAIL server registry entries.
    """

    version: Literal[1] = 1
    entries: dict[str, SwarmRegistryEntry] = Field(default_factory=dict)


SwarmRegistry = dict[str, SwarmRegistryEntry]
