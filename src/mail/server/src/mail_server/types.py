# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Response
from mail_protocol.core.address import MAILAddress
from mail_protocol.core.message import MAILMessage, MAILMessageType
from mail_protocol.interswarm.message import MAILInterswarmMessage
from pydantic import BaseModel

EndpointFunction = Callable[..., Awaitable[Response]]
Metadata = dict[str, Any]
PostMessageHandler = Callable[[MAILMessage], Awaitable[tuple[MAILMessage, Metadata]]]
PostInterswarmMessageHandler = Callable[[MAILInterswarmMessage], Awaitable[tuple[MAILInterswarmMessage, Metadata]]]


class PostMessageRequest(BaseModel):
    """
    A request body to the endpoint `POST /message`.
    """
    task_id: str
    msg_type: MAILMessageType
    subject: str
    body: str
    recipients: list[MAILAddress]
    metadata: Metadata


class PostMessageResponse(BaseModel):
    """
    A response body to the endpoint `POST /message`.
    """
    message: MAILMessage
    metadata: Metadata


class PostInterswarmMessageRequest(BaseModel):
    """
    A request body to the endpoint `POST /interswarm/message`.
    """
    message: MAILInterswarmMessage
    metadata: Metadata


class PostInterswarmMessageResponse(BaseModel):
    """
    A response body to the endpoint `POST /interswarm/message`.
    """
    message: MAILInterswarmMessage
    metadata: Metadata