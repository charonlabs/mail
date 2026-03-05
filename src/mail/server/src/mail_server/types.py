# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from collections.abc import Awaitable, Callable

from fastapi import Response
from mail_protocol.core.address import MAILAddress
from mail_protocol.core.message import MAILMessage, MAILMessageType
from mail_protocol.interswarm import MAILRemoteSwarm
from mail_protocol.interswarm.message import MAILInterswarmMessage
from mail_protocol.metadata import Metadata
from pydantic import BaseModel

EndpointFunction = Callable[..., Awaitable[Response]]
PostMessageHandler = Callable[[MAILMessage], Awaitable[tuple[MAILMessage, Metadata]]]
PostInterswarmMessageHandler = Callable[[MAILInterswarmMessage], Awaitable[tuple[bool, str, str]]]
SwarmRegistry = dict[str, tuple[MAILRemoteSwarm, bool, bool]]
