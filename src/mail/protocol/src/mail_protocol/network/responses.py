# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.drafts import MAILDraftsEntry, MAILDraftsEntrySummary
from mail_protocol.core.inbox import MAILInboxEntry, MAILInboxEntrySummary
from mail_protocol.core.lists import MAILListInBackend
from mail_protocol.core.messages import MAILMessage, MAILMessageSummary
from mail_protocol.core.outbox import MAILOutboxEntry, MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm, MAILSwarmSummary
from mail_protocol.core.trash import MAILTrashEntry, MAILTrashEntrySummary
from mail_protocol.core.user_agents import (
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
)
from mail_protocol.core.validators import (
    validate_daemon_worker_names,
    validate_local_addresses,
    validate_user_names,
)
from mail_protocol.core.webhooks import MAILWebhook


#
# Top-level endpoints
#
class RootGetResponse(BaseModel):
    """
    Corresponds to `GET /`.
    Contains basic MAIL server information and metadata.
    """

    protocol_name: Literal["mail"]
    protocol_version: Literal["2.0"]
    uptime: float


class HealthGetResponse(BaseModel):
    """
    Corresponds to `GET /health`.
    Contains a basic health status message (should be ok).
    """

    status: Literal["ok"]


#
# Authentication endpoints
#
class AuthTokenPostResponse(BaseModel):
    """
    Corresponds to `POST /auth/token`.
    Contains a temporary JWT and associated metadata.

    ``refresh_token`` is populated only for interactive principals (users and
    admins); agents and daemons re-authenticate with their credentials and
    receive ``None``. When present, the server also sets it as an ``httpOnly``
    cookie for browser clients. ``expires_in`` is the access-token lifetime in
    seconds.
    """

    access_token: str
    token_type: Literal["bearer"]
    refresh_token: str | None = None
    expires_in: int
    metadata: dict[str, Any]


class AuthRefreshPostResponse(BaseModel):
    """
    Corresponds to `POST /auth/refresh`.
    Contains a freshly-minted access token and a rotated refresh token.

    Mirrors `AuthTokenPostResponse`. The previous refresh token is invalidated
    on every successful refresh; ``refresh_token`` carries its replacement (also
    rotated in the ``httpOnly`` cookie for browser clients).
    """

    access_token: str
    token_type: Literal["bearer"]
    refresh_token: str | None = None
    expires_in: int
    metadata: dict[str, Any]


class AuthLogoutPostResponse(BaseModel):
    """
    Corresponds to `POST /auth/logout`.
    Contains a message indicating operation success.
    """

    status: Literal["success"]


class AuthWhoamiGetResponse(BaseModel):
    """
    Corresponds to `GET /auth/whoami`.
    Contains current user information and metadata.
    """

    user_agent: MAILUserAgent
    metadata: dict[str, Any]


class AuthPasswordResetResponse(BaseModel):
    """
    Corresponds to `POST /auth/password/reset`.
    Contains a message indicating operation success.
    """

    status: Literal["success"]


#
# Swarm endpoints
#
class SwarmsGetResponse(BaseModel):
    """
    Corresponds to `GET /swarms`.
    Contains the list of swarms exposed by this server.
    """

    swarms: list[MAILSwarmSummary]
    metadata: dict[str, Any]


class SwarmGetResponse(BaseModel):
    """
    Corresponds to `GET /swarms/{swarm_name}`.
    Contains information about the specified existing + exposed MAIL swarm.
    """

    swarm: MAILSwarm
    metadata: dict[str, Any]


class SwarmHealthGetResponse(BaseModel):
    """
    Corresponds to `GET /swarms/{swarm_name}/health`.
    Contains up-to-date, swarm-specific health information.
    """

    status: Literal["ok"]


#
# Inbox endpoints
#
class InboxGetResponse(BaseModel):
    """
    Corresponds to `GET /inbox`.
    Contains a list of entries in the user-agent's inbox.
    """

    entries: list[MAILInboxEntrySummary]
    metadata: dict[str, Any]


class InboxMessageGetResponse(BaseModel):
    """
    Corresponds to `GET /inbox/{message_id}`.
    Contains a specific entry by message ID inside the user-agent's inbox.
    """

    entry: MAILInboxEntry
    metadata: dict[str, Any]


class InboxMessageDeleteResponse(BaseModel):
    """
    Corresponds to `DELETE /inbox/{message_id}`.
    Contains a specific entry by message ID that was moved from the user-agent's inbox to trash.
    """

    entry: MAILInboxEntry
    metadata: dict[str, Any]


#
# Outbox endpoints
#
class OutboxGetResponse(BaseModel):
    """
    Corresponds to `GET /outbox`.
    Contains a list of entries in the user-agent's outbox.
    """

    entries: list[MAILOutboxEntrySummary]
    metadata: dict[str, Any]


class OutboxMessageGetResponse(BaseModel):
    """
    Corresponds to `GET /outbox/{message_id}`.
    Contains a specific entry by message ID inside the user-agent's outbox.
    """

    entry: MAILOutboxEntry
    metadata: dict[str, Any]


#
# Draft endpoints
#
class DraftsGetResponse(BaseModel):
    """
    Corresponds to `GET /drafts`.
    Contains a list of entries in the user-agent's drafts box.
    """

    entries: list[MAILDraftsEntrySummary]
    metadata: dict[str, Any]


class DraftPostResponse(BaseModel):
    """
    Corresponds to `POST /drafts`.
    Contains the new entry in the user-agent's drafts box.
    """

    entry: MAILDraftsEntry
    metadata: dict[str, Any]


class DraftGetResponse(BaseModel):
    """
    Corresponds to `GET /drafts/{draft_id}`.
    Contains a specific message draft inside the user-agent's drafts box.
    """

    entry: MAILDraftsEntry
    metadata: dict[str, Any]


class DraftPatchResponse(BaseModel):
    """
    Corresponds to `PATCH /drafts/{draft_id}`.
    Contains the updated message draft in the user-agent's drafts box.
    """

    entry: MAILDraftsEntry
    metadata: dict[str, Any]


class DraftDeleteResponse(BaseModel):
    """
    Corresponds to `DELETE /drafts/{draft_id}`.
    Contains the specific message draft deleted from the user-agent's drafts box.
    """

    entry: MAILDraftsEntry
    metadata: dict[str, Any]


class DraftSendPostResponse(BaseModel):
    """
    Corresponds to `POST /drafts/{draft_id}/send`.
    Contains the assembled MAIL message to be delivered.
    """

    message: MAILMessage
    metadata: dict[str, Any]


#
# Trash endpoints
#
class TrashGetResponse(BaseModel):
    """
    Corresponds to `GET /trash`.
    Contains a list of messages in the user-agent's trash box.
    """

    entries: list[MAILTrashEntrySummary]
    metadata: dict[str, Any]


class TrashMessageGetResponse(BaseModel):
    """
    Corresponds to `GET /trash/{message_id}`.
    Contains the specific trashed message by ID from the user-agent's trash box.
    """

    entry: MAILTrashEntry
    metadata: dict[str, Any]


class TrashMessageDeleteResponse(BaseModel):
    """
    Corresponds to `DELETE /trash/{message_id}`.
    Contains the specific message deleted from the user-agent's trash box.
    """

    entry: MAILTrashEntry
    metadata: dict[str, Any]


class TrashClearPostResponse(BaseModel):
    """
    Corresponds to `POST /trash/clear`.
    Contains the list of messages deleted from the user-agent's trash box.
    """

    entries: list[MAILTrashEntrySummary]
    metadata: dict[str, Any]


#
# Daemon endpoints
#
class DaemonMessageBufferClearResponse(BaseModel):
    """
    Corresponds to `POST /daemon/message-buffer/clear`.
    Contains the IDs of all MAIL messages on the server to be delivered by the daemon.
    """

    message_ids: list[str]
    metadata: dict[str, Any]


class DaemonDeliverLocalResponse(BaseModel):
    """
    Corresponds to `POST /daemon/deliver/local`.
    Contains the list of messages successfully delivered to server-local user-agents.
    """

    messages: list[MAILMessageSummary]
    metadata: dict[str, Any]


class DaemonDeliverRemoteResponse(BaseModel):
    """
    Corresponds to `POST /daemon/deliver/remote`.
    Contains the list of messages successfully delivered to server-local user-agents.
    """

    messages: list[MAILMessageSummary]
    metadata: dict[str, Any]


#
# Administrator endpoints
#
class AdminAgentsGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/agents`.
    Contains the list of agents by local address (name@swarm) registered on this MAIL server.
    """

    agents: Annotated[list[str], AfterValidator(validate_local_addresses)]
    metadata: dict[str, Any]


class AdminAgentGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/agents/{local_address}`.
    Contains a specific MAIL agent registered on this server.
    """

    agent: MAILAgent
    metadata: dict[str, Any]


class AdminAgentPostResponse(BaseModel):
    """
    Corresponds to `POST /admin/agents`.
    Contains the new MAIL agent registered on this server.
    """

    agent: MAILAgent
    metadata: dict[str, Any]


class AdminAgentDeleteResponse(BaseModel):
    """
    Corresponds to `DELETE /admin/agents/{local_address}`.
    Contains a newly-deleted MAIL agent registered on this server.
    """

    agent: MAILAgent
    metadata: dict[str, Any]


class AdminDaemonsGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/daemons`.
    Contains the list of daemons by worker name registered on this MAIL server.
    """

    daemons: Annotated[list[str], AfterValidator(validate_daemon_worker_names)]
    metadata: dict[str, Any]


class AdminDaemonGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/daemons/{worker_name}`.
    Contains a specific MAIL daemon registered on this server.
    """

    daemon: MAILDaemon
    metadata: dict[str, Any]


class AdminDaemonPostResponse(BaseModel):
    """
    Corresponds to `POST /admin/daemons`.
    Contains the new MAIL daemon registered on this server.
    """

    daemon: MAILDaemon
    metadata: dict[str, Any]


class AdminDaemonDeleteResponse(BaseModel):
    """
    Corresponds to `DELETE /admin/daemons/{worker_name}`.
    Contains a newly-deleted MAIL daemon registered on this server.
    """

    daemon: MAILDaemon
    metadata: dict[str, Any]


class AdminUsersGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/users`.
    Contains a list of users by username registered on this MAIL server.
    """

    users: Annotated[list[str], AfterValidator(validate_user_names)]
    metadata: dict[str, Any]


class AdminUserGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/users/{user_id}`.
    Contains a specific MAIL user registered on this server.
    """

    user: MAILUser
    metadata: dict[str, Any]


class AdminUserPostResponse(BaseModel):
    """
    Corresponds to `POST /admin/users`.
    Contains the new MAIL user registered on this server.
    """

    user: MAILUser
    metadata: dict[str, Any]


class AdminUserDeleteResponse(BaseModel):
    """
    Corresponds to `DELETE /admin/users/{user_id}`.
    Contains a newly-deleted MAIL user registered on this server.
    """

    user: MAILUser
    metadata: dict[str, Any]


class AdminSwarmPostResponse(BaseModel):
    """
    Corresponds to `POST /admin/swarms`.
    Contains info on the newly-created MAIL swarm on this server.
    """

    swarm: MAILSwarm
    metadata: dict[str, Any]


class AdminSwarmDeleteResponse(BaseModel):
    """
    Corresponds to `DELETE /admin/swarms/{swarm_name}`.
    Contains info on the newly-deleted MAIL swarm on this server.
    """

    swarm: MAILSwarm
    metadata: dict[str, Any]


class AdminWebhooksGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/webhooks`.
    Contains a list of existing webhooks by ID.
    """

    webhook_ids: list[str]
    metadata: dict[str, Any]


class AdminWebhookGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/webhooks/{webhook_id}`.
    Contains info on the existing webhook by ID.
    """

    webhook: MAILWebhook
    metadata: dict[str, Any]


class AdminWebhooksPostResponse(BaseModel):
    """
    Corresponds to `POST /admin/webhooks`.
    Contains information on the newly-created webhook.
    """

    webhook: MAILWebhook
    metadata: dict[str, Any]


class AdminWebhooksPatchResponse(BaseModel):
    """
    Corresponds to `PATCH /admin/webhooks/{webhook_id}`.
    Contains information on the patched webhook.
    """

    webhook: MAILWebhook
    metadata: dict[str, Any]


class AdminWebhooksDeleteResponse(BaseModel):
    """
    Corresponds to `DELETE /admin/webhooks/{webhook_id}`.
    Contains information on the newly-deleted webhook.
    """

    webhook: MAILWebhook
    metadata: dict[str, Any]


#
# List endpoints
#
class AdminListsGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/lists`. All lists known to the server.
    """

    lists: list[MAILListInBackend]
    metadata: dict[str, Any]


class AdminListGetResponse(BaseModel):
    """
    Corresponds to `GET /admin/lists/{local_address}`.
    """

    mail_list: MAILListInBackend
    metadata: dict[str, Any]


class AdminListPostResponse(BaseModel):
    """
    Corresponds to `POST /admin/lists`.
    """

    mail_list: MAILListInBackend
    metadata: dict[str, Any]


class AdminListPatchResponse(BaseModel):
    """
    Corresponds to `PATCH /admin/lists/{local_address}`.
    """

    mail_list: MAILListInBackend
    metadata: dict[str, Any]


class AdminListDeleteResponse(BaseModel):
    """
    Corresponds to `DELETE /admin/lists/{local_address}`.
    """

    mail_list: MAILListInBackend
    metadata: dict[str, Any]


class ListsGetResponse(BaseModel):
    """
    Corresponds to `GET /lists`. Returns lists visible to the caller.
    At v1 every list has ``visibility = "public"``; future versions
    that introduce private lists will filter here.
    """

    lists: list[MAILListInBackend]
    metadata: dict[str, Any]


class ListGetResponse(BaseModel):
    """
    Corresponds to `GET /lists/{local_address}`.
    """

    mail_list: MAILListInBackend
    metadata: dict[str, Any]


class ListMemberPostResponse(BaseModel):
    """
    Corresponds to `POST /lists/{local_address}/subscribe` and
    `POST /admin/lists/{local_address}/members`. The updated list with
    the member appended (idempotent — re-adding an existing member is
    a no-op).
    """

    mail_list: MAILListInBackend
    metadata: dict[str, Any]


class ListMemberDeleteResponse(BaseModel):
    """
    Corresponds to `POST /lists/{local_address}/unsubscribe`
    and `DELETE /admin/lists/{local_address}/members/{member_address}`.
    The updated list with the member removed (idempotent — removing a
    non-member is a no-op).
    """

    mail_list: MAILListInBackend
    metadata: dict[str, Any]
