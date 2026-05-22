# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from typing import Any, Literal

from pydantic import BaseModel

from mail_protocol.core.drafts import MAILDraftsEntry, MAILDraftsEntrySummary
from mail_protocol.core.inbox import MAILInboxEntry, MAILInboxEntrySummary
from mail_protocol.core.messages import MAILMessage, MAILMessageSummary
from mail_protocol.core.outbox import MAILOutboxEntry, MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm, MAILSwarmSummary
from mail_protocol.core.trash import MAILTrashEntry, MAILTrashEntrySummary
from mail_protocol.core.user_agents import MAILUserAgent


#
# Top-level endpoints
#
class GetRootResponse(BaseModel):
    """
    Corresponds to `GET /`.
    Contains basic MAIL server information and metadata.
    """

    protocol_name: Literal["mail"]
    protocol_version: Literal["2.0"]
    uptime: float


class GetHealthResponse(BaseModel):
    """
    Corresponds to `GET /health`.
    Contains a basic health status message (should be ok).
    """

    status: Literal["ok"]


#
# Authentication endpoints
#
class PostAuthTokenResponse(BaseModel):
    """
    Corresponds to `POST /auth/token`.
    Contains a temporary JWT and associated metadata.
    """

    access_token: str
    token_type: Literal["bearer"]
    metadata: dict[str, Any]


class GetAuthWhoamiResponse(BaseModel):
    """
    Corresponds to `GET /auth/whoami`.
    Contains current user information and metadata.
    """

    user_agent: MAILUserAgent
    metadata: dict[str, Any]


#
# Swarm endpoints
#
class GetSwarmsResponse(BaseModel):
    """
    Corresponds to `GET /swarms`.
    Contains the list of swarms exposed by this server.
    """

    swarms: list[MAILSwarmSummary]
    metadata: dict[str, Any]


class GetSwarmResponse(BaseModel):
    """
    Corresponds to `GET /swarms/{swarm_name}`.
    Contains information about the specified existing + exposed MAIL swarm.
    """

    swarm: MAILSwarm
    metadata: dict[str, Any]


class GetSwarmHealthResponse(BaseModel):
    """
    Corresponds to `GET /swarms/{swarm_name}/health`.
    Contains up-to-date, swarm-specific health information.
    """

    status: Literal["ok"]


#
# Inbox endpoints
#
class GetInboxResponse(BaseModel):
    """
    Corresponds to `GET /inbox`.
    Contains a list of entries in the user-agent's inbox.
    """

    entries: list[MAILInboxEntrySummary]
    metadata: dict[str, Any]


class GetInboxMessageResponse(BaseModel):
    """
    Corresponds to `GET /inbox/{message_id}`.
    Contains a specific entry by message ID inside the user-agent's inbox.
    """

    entry: MAILInboxEntry
    metadata: dict[str, Any]


class DeleteInboxMessageResponse(BaseModel):
    """
    Corresponds to `DELETE /inbox/{message_id}`.
    Contains a specific entry by message ID that was moved from the user-agent's inbox to trash.
    """

    entry: MAILInboxEntry
    metadata: dict[str, Any]


#
# Outbox endpoints
#
class GetOutboxResponse(BaseModel):
    """
    Corresponds to `GET /outbox`.
    Contains a list of entries in the user-agent's outbox.
    """

    entries: list[MAILOutboxEntrySummary]
    metadata: dict[str, Any]


class GetOutboxMessageResponse(BaseModel):
    """
    Corresponds to `GET /outbox/{message_id}`.
    Contains a specific entry by message ID inside the user-agent's outbox.
    """

    entry: MAILOutboxEntry
    metadata: dict[str, Any]


#
# Draft endpoints
#
class GetDraftsResponse(BaseModel):
    """
    Corresponds to `GET /drafts`.
    Contains a list of entries in the user-agent's drafts box.
    """

    entries: list[MAILDraftsEntrySummary]
    metadata: dict[str, Any]


class PostDraftResponse(BaseModel):
    """
    Corresponds to `POST /drafts`.
    Contains the new entry in the user-agent's drafts box.
    """

    entry: MAILDraftsEntry
    metadata: dict[str, Any]


class GetDraftResponse(BaseModel):
    """
    Corresponds to `GET /drafts/{draft_id}`.
    Contains a specific message draft inside the user-agent's drafts box.
    """

    entry: MAILDraftsEntry
    metadata: dict[str, Any]


class DeleteDraftResponse(BaseModel):
    """
    Corresponds to `DELETE /drafts/{draft_id}`.
    Contains the specific message draft deleted from the user-agent's drafts box.
    """

    entry: MAILDraftsEntry
    metadata: dict[str, Any]


class PostDraftSendResponse(BaseModel):
    """
    Corresponds to `POST /drafts/{draft_id}/send`.
    Contains the assembled MAIL message to be delivered.
    """

    message: MAILMessage
    metadata: dict[str, Any]


#
# Trash endpoints
#
class GetTrashResponse(BaseModel):
    """
    Corresponds to `GET /trash`.
    Contains a list of messages in the user-agent's trash box.
    """

    entries: list[MAILTrashEntrySummary]
    metadata: dict[str, Any]


class GetTrashMessageResponse(BaseModel):
    """
    Corresponds to `GET /trash/{message_id}`.
    Contains the specific trashed message by ID from the user-agent's trash box.
    """

    entry: MAILTrashEntry
    metadata: dict[str, Any]


class DeleteTrashMessageResponse(BaseModel):
    """
    Corresponds to `DELETE /trash/{message_id}`.
    Contains the specific message deleted from the user-agent's trash box.
    """

    entry: MAILTrashEntry
    metadata: dict[str, Any]


class PostTrashClearResponse(BaseModel):
    """
    Corresponds to `POST /trash/clear`.
    Contains the list of messages deleted from the user-agent's trash box.
    """

    entries: list[MAILTrashEntrySummary]
    metadata: dict[str, Any]


#
# Daemon endpoints
#
class PostDaemonMessageBufferClearResponse(BaseModel):
    """
    Corresponds to `POST /daemon/message-buffer/clear`.
    Contains the IDs of all MAIL messages on the server to be delivered by the daemon.
    """

    message_ids: list[str]
    metadata: dict[str, Any]


class PostDaemonDeliverLocalResponse(BaseModel):
    """
    Corresponds to `POST /daemon/deliver/local`.
    Contains the list of messages successfully delivered to server-local user-agents.
    """

    messages: list[MAILMessageSummary]
    metadata: dict[str, Any]


class PostDaemonDeliverRemoteResponse(BaseModel):
    """
    Corresponds to `POST /daemon/deliver/remote`.
    Contains the list of messages successfully delivered to server-local user-agents.
    """

    messages: list[MAILMessageSummary]
    metadata: dict[str, Any]
