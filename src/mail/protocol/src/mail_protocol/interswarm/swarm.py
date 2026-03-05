# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import urllib.parse
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.swarm import validate_description, validate_keywords
from mail_protocol.metadata import Metadata


def validate_swarm_name(swarm_name: str) -> str:
    """
    Validate a MAIL swarm name.
    """
    if not swarm_name.strip():
        raise ValueError(f"Invalid MAIL swarm name: {swarm_name}")
    return swarm_name


def validate_uri(uri: str) -> str:
    """
    Validate a URI string.
    """
    if not uri.strip():
        raise ValueError(f"Invalid URI: {uri}")
    result = urllib.parse.urlsplit(uri)
    if (result.scheme != "https") and (result.scheme != "http") and (result.scheme != "swarm"):
        raise ValueError(f"Invalid URI: {uri}")
    if not result.netloc.strip():
        raise ValueError(f"Invalid URI: {uri}")
    
    return uri


def validate_optional_timestamp(timestamp: str | None) -> str | None:
    """
    Validate a timestamp string.
    """
    if timestamp is None:
        return None
    try:
        datetime.fromisoformat(timestamp)
    except ValueError:
        raise ValueError(f"Invalid timestamp: {timestamp}")
    return timestamp


class MAILRemoteSwarm(BaseModel):
    """
    A MAIL remote swarm.
    """
    name: Annotated[str, AfterValidator(validate_swarm_name)]
    base_url: Annotated[str, AfterValidator(validate_uri)]
    protocol_version: str
    active: bool
    last_seen: Annotated[str | None, AfterValidator(validate_optional_timestamp)]
    description: Annotated[str | None, AfterValidator(validate_description)]
    keywords: Annotated[list[str], AfterValidator(validate_keywords)]
    metadata: Metadata