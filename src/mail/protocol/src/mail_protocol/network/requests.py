# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.address import MAILAddress
from mail_protocol.core.message import MAILMessageType
from mail_protocol.interswarm.message import MAILInterswarmMessage
from mail_protocol.metadata import Metadata


class LoginRequest(BaseModel):
    """
    A request body to the endpoint `POST /login`.
    """
    api_key: str


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


class PostInterswarmMessageRequest(BaseModel):
    """
    A request body to the endpoint `POST /interswarm/message`.
    """
    message: MAILInterswarmMessage
    metadata: Metadata


def validate_base_url(base_url: str) -> str:
    """
    Validate a base URL string.
    """
    result = urlsplit(base_url)
    if result.scheme != "https" and result.scheme != "http" and result.scheme != "swarm":
        raise ValueError(f"Invalid base URL: {base_url}")
    if not result.netloc.strip():
        raise ValueError(f"Invalid base URL: {base_url}")
    return base_url


class PostRegistryRequest(BaseModel):
    """
    A request body to the endpoint `POST /registry`.
    """
    base_url: Annotated[str, AfterValidator(validate_base_url)]
    api_key_ref: str
    public: bool
    volatile: bool
    metadata: Metadata