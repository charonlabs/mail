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
    version: str
    """The version of the swarm."""
    health_check_url: str
    """The health check endpoint URL."""
    auth_token_ref: str | None
    """Authentication token reference (environment variable or actual token)."""
    last_seen: datetime.datetime | None
    """When this swarm was last seen/heard from."""
    is_active: bool
    """Whether this swarm is currently active."""
    latency: float | None
    """The latency of the swarm in seconds."""
    swarm_description: str
    """The description of the swarm."""
    keywords: list[str]
    """The keywords of the swarm."""
    metadata: dict[str, Any] | None
    """Additional metadata about the swarm."""
    public: bool
    """Whether this swarm is publicly accessible."""
    volatile: bool
    """Whether this swarm is volatile (will be removed from the registry when the server shuts down)."""


class SwarmEndpointCleaned(TypedDict):
    """
    Represents a swarm endpoint for interswarm communication.
    """

    swarm_name: str
    """The name of the swarm."""
    base_url: str
    """The base URL of the swarm (e.g., https://swarm1.example.com)."""
    version: str
    """The protocol version of the swarm."""
    last_seen: datetime.datetime | None
    """When this swarm was last seen/heard from."""
    is_active: bool
    """Whether this swarm is currently active."""
    latency: float | None
    """The latency of the swarm in seconds."""
    swarm_description: str
    """The description of the swarm."""
    keywords: list[str]
    """The keywords of the swarm."""
    metadata: dict[str, Any] | None
    """Additional metadata about the swarm."""


class SwarmInfo(TypedDict):
    """
    Information about the current swarm.
    """

    name: str
    """The name of the swarm."""
    version: str
    """The protocol version of the swarm."""
    description: str
    """The description of the swarm."""
    entrypoint: str
    """The default entrypoint of the swarm."""
    keywords: list[str]
    """The keywords of the swarm."""
    public: bool
    """Whether this swarm is publicly accessible."""


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
    protocol_version: str
    """The version of the MAIL protocol that is being used."""
    swarm: SwarmInfo
    """Information about the swarm that is running."""
    status: str
    """The status of the service; should always be `running`."""
    uptime: float
    """The uptime of the service in seconds."""


class GetWhoamiResponse(TypedDict):
    """
    Response for the MAIL server endpoint `GET /whoami`.
    """

    id: str
    """The ID of the caller."""
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

    swarms: list[SwarmEndpointCleaned]
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


class PostInterswarmForwardResponse(TypedDict):
    """
    Response for the MAIL server endpoint `POST /interswarm/forward`.
    """

    swarm: str
    """The name of the swarm."""
    task_id: str
    """The task ID of the interswarm message."""
    status: str
    """The status of the response."""
    local_runner: str
    """The local runner of the swarm (role:id@swarm)."""


class PostInterswarmBackResponse(TypedDict):
    """
    Response for the MAIL server endpoint `POST /interswarm/back`.
    """

    swarm: str
    """The name of the swarm."""
    task_id: str
    """The task ID of the interswarm message."""
    status: str
    """The status of the response."""
    local_runner: str
    """The local runner of the swarm (role:id@swarm)."""


class PostSwarmsLoadResponse(TypedDict):
    """
    Response for the MAIL server endpoint `POST /swarms/load`.
    """

    status: str
    """The status of the response."""
    swarm_name: str
    """The name of the swarm."""
