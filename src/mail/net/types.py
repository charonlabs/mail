# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
from typing import Any, TypedDict

from sse_starlette import ServerSentEvent

from mail.core.message import MAILMessage


class SwarmEndpoint(TypedDict):
    """
    Represents a swarm endpoint for interswarm communication.
    """

    swarm_name: str
    """The name of the swarm."""
    base_url: str
    """The base URL of the swarm (e.g., https://swarm1.example.com)."""
    health_check_url: str
    """The health check endpoint URL."""
    auth_token_ref: str | None
    """Authentication token reference (environment variable or actual token)."""
    last_seen: datetime.datetime | None
    """When this swarm was last seen/heard from."""
    is_active: bool
    """Whether this swarm is currently active."""
    metadata: dict[str, Any] | None
    """Additional metadata about the swarm."""
    volatile: bool
    """Whether this swarm is volatile (will be removed from the registry when the server shuts down)."""


class SwarmStatus(TypedDict):
    """
    The status of a swarm.
    """

    name: str | None
    """The name of the swarm."""
    status: str
    """The status of the swarm."""


class GetRootResponse(TypedDict):
    """
    Response for the MAIL server endpoint `GET /`.
    """

    name: str
    """The name of the service; should always be `mail`."""
    version: str
    """The version of MAIL that is running."""
    swarm: str
    """The name of the swarm that is running."""
    status: str
    """The status of the service; should always be `running`."""
    uptime: float
    """The uptime of the service in seconds."""


class GetWhoamiResponse(TypedDict):
    """
    Response for the MAIL server endpoint `GET /whoami`.
    """

    username: str
    """The username of the caller."""
    role: str
    """The role of the caller."""


class GetStatusResponse(TypedDict):
    """
    Response for the MAIL server endpoint `GET /status`.
    """

    swarm: SwarmStatus
    """The swarm that is running."""
    active_users: int
    """The number of active users."""
    user_mail_ready: bool
    """Whether the user MAIL instance is ready."""
    user_task_running: bool
    """Whether the user MAIL instance task is running."""


class PostMessageResponse(TypedDict):
    """
    Response for the MAIL server endpoint `POST /message`.
    """

    response: str
    """The response from the MAIL instance."""

    events: list[ServerSentEvent] | None
    """The events from the MAIL instance."""


class GetHealthResponse(TypedDict):
    """
    Response for the MAIL server endpoint `GET /health`.
    """

    status: str
    """The status of the MAIL instance."""

    swarm_name: str
    """The name of the swarm."""

    timestamp: str
    """The timestamp of the response."""


class GetSwarmsResponse(TypedDict):
    """
    Response for the MAIL server endpoint `GET /swarms`.
    """

    swarms: list[SwarmEndpoint]
    """The swarms that are running."""


class PostSwarmsResponse(TypedDict):
    """
    Response for the MAIL server endpoint `POST /swarms`.
    """

    status: str
    """The status of the response."""

    swarm_name: str
    """The name of the swarm."""


class GetSwarmsDumpResponse(TypedDict):
    """
    Response for the MAIL server endpoint `GET /swarms/dump`.
    """

    status: str
    """The status of the response."""

    swarm_name: str
    """The name of the swarm."""


class PostInterswarmMessageResponse(TypedDict):
    """
    Response for the MAIL server endpoint `POST /interswarm/message`.
    """

    response: MAILMessage
    """The response from the MAIL instance."""

    events: list[ServerSentEvent] | None
    """The events from the MAIL instance."""


class PostInterswarmResponseResponse(TypedDict):
    """
    Response for the MAIL server endpoint `POST /interswarm/response`.
    """

    status: str
    """The status of the response."""

    task_id: str
    """The task ID of the response."""


class PostInterswarmSendResponse(TypedDict):
    """
    Response for the MAIL server endpoint `POST /interswarm/send`.
    """

    response: MAILMessage
    """The response from the MAIL instance."""

    events: list[ServerSentEvent] | None
    """The events from the MAIL instance."""


class PostSwarmsLoadResponse(TypedDict):
    """
    Response for the MAIL server endpoint `POST /swarms/load`.
    """

    status: str
    """The status of the response."""

    swarm_name: str
    """The name of the swarm."""
