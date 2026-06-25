# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from mail_protocol.core.lists import MAILListPolicy
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.validators import (
    validate_agent_name,
    validate_daemon_worker_name,
    validate_list_name,
    validate_mail_address,
    validate_mail_addresses,
    validate_message_body,
    validate_message_recipients,
    validate_message_subject,
    validate_message_tags,
    validate_swarm_description,
    validate_swarm_keywords,
    validate_swarm_name,
    validate_url,
    validate_user_name,
    validate_uuid,
    validate_uuids,
    validate_webhook_event_types,
)


#
# Authentication endpoints
#
class AuthTokenPostRequest(BaseModel):
    """
    Submit valid credentials to obtain a JWT for subsequent use.
    """

    pass


class AuthPasswordResetRequest(BaseModel):
    """
    Corresponds to `POST /auth/password/reset`.
    Contains user's current password and desired new password.
    """

    current_password: str
    new_password: str


#
# Draft endpoints
#
class DraftPostRequest(BaseModel):
    """
    Corresponds to `POST /drafts/`.
    Contains relevant information for creating a new MAIL message draft.

    `reply_to` optionally references the `message_id` of the message this
    draft is replying to. `tags` is an optional list of sender-defined slug
    strings used to categorize the eventual message.
    """

    subject: Annotated[str, AfterValidator(validate_message_subject)]
    body: Annotated[str, AfterValidator(validate_message_body)]
    reply_to: Annotated[str, AfterValidator(validate_uuid)] | None = None
    tags: Annotated[list[str], AfterValidator(validate_message_tags)] = []


class DraftPatchRequest(BaseModel):
    """
    Corresponds to `PATCH /drafts/{draft_id}`.
    Contains the fields to update on an existing MAIL message draft.

    Every field is optional: a field left unset (``None``) is not modified,
    so callers can patch a single field without resending the rest. The one
    asymmetry is ``tags`` — sending ``tags: []`` clears all tags, while
    omitting ``tags`` leaves the existing tags untouched.
    """

    subject: Annotated[str, AfterValidator(validate_message_subject)] | None = None
    body: Annotated[str, AfterValidator(validate_message_body)] | None = None
    reply_to: Annotated[str, AfterValidator(validate_uuid)] | None = None
    tags: Annotated[list[str], AfterValidator(validate_message_tags)] | None = None


class DraftSendPostRequest(BaseModel):
    """
    Corresponds to `POST /drafts/{draft_id}/send`.
    Contains relevant information for sending an existing draft as a MAIL message.

    `tags` is an optional list of sender-defined slug strings; any tags
    supplied here are merged (union, order-preserving) with the tags already
    stored on the draft.
    """

    recipients: Annotated[list[str], AfterValidator(validate_message_recipients)]
    tags: Annotated[list[str], AfterValidator(validate_message_tags)] = []


#
# Trash endpoints
#
class TrashClearPostRequest(BaseModel):
    """
    Corresponds to `POST /trash/clear`.
    No body for this endpoint.
    """

    pass


#
# Daemon endpoints
#
class DaemonDeliverLocalRequest(BaseModel):
    """
    Corresponds to `POST /daemon/deliver/local`.
    Contains a list of local message IDs to deliver to their intended local targets.
    """

    message_ids: Annotated[list[str], AfterValidator(validate_uuids)]


class DaemonDeliverRemoteRequest(BaseModel):
    """
    Corresponds to `POST /daemon/deliver/remote`.
    Contains a list of remote MAIL messages to deliver to their intended local targets.
    """

    messages: list[MAILMessage]


#
# Administrator endpoints
#
class AdminAgentPostRequest(BaseModel):
    """
    Corresponds to `POST /admin/agents`.
    Contains an agent name, swarm, and password to register with.
    """

    agent_name: Annotated[str, AfterValidator(validate_agent_name)]
    swarm_name: Annotated[str, AfterValidator(validate_swarm_name)]
    agent_password: str


class AdminDaemonPostRequest(BaseModel):
    """
    Corresponds to `POST /admin/daemons`.
    Contains a worker name and password to register with.
    """

    worker_name: Annotated[str, AfterValidator(validate_daemon_worker_name)]
    daemon_password: str


class AdminUserPostRequest(BaseModel):
    """
    Corresponds to `POST /admin/users`.
    Contains a user ID and password to register with.
    """

    user_id: Annotated[str, AfterValidator(validate_user_name)]
    user_password: str


class AdminSwarmPostRequest(BaseModel):
    """
    Corresponds to `POST /admin/swarms`.
    Contains basic info necessary for new MAIL swarm creation.
    """

    name: Annotated[str, AfterValidator(validate_swarm_name)]
    description: Annotated[str, AfterValidator(validate_swarm_description)]
    keywords: Annotated[list[str], AfterValidator(validate_swarm_keywords)]


class AdminWebhooksPostRequest(BaseModel):
    """
    Corresponds to `POST /admin/webhooks`.
    Contains info required for webhook setup.
    """

    url: Annotated[str, AfterValidator(validate_url)]
    events: Annotated[list[str], AfterValidator(validate_webhook_event_types)]
    secret: str


class AdminWebhooksPatchRequest(BaseModel):
    """
    Corresponds to `PATCH /admin/webhooks`.
    Allows client to change URL or secret for an existing webhook.
    """

    url: Annotated[str, AfterValidator(validate_url)]
    secret: str


class AdminListPostRequest(BaseModel):
    """
    Corresponds to `POST /admin/lists`.
    Contains the descriptive fields needed to create a new MAIL list.
    """

    name: Annotated[str, AfterValidator(validate_list_name)]
    swarm_name: Annotated[str, AfterValidator(validate_swarm_name)]
    owner: Annotated[str, AfterValidator(validate_mail_address)]
    members: Annotated[list[str], AfterValidator(validate_mail_addresses)] = []
    policy: MAILListPolicy = MAILListPolicy()


class AdminListPatchRequest(BaseModel):
    """
    Corresponds to `PATCH /admin/lists/{local_address}`.

    All fields are optional; only the policy is mutable at v1. The
    canonical address (name, swarm, host) is immutable for the life of
    the list — re-create + cut over if a rename is required.
    """

    policy: MAILListPolicy | None = None


class ListMemberPostRequest(BaseModel):
    """
    Corresponds to ``POST /lists/{local_address}/subscribe``
    and ``POST /admin/lists/{local_address}/members``.

    ``member_address`` is the address being added. For the public
    subscribe path, this must match the authenticated bearer
    (self-subscribe); for the admin add path, any valid MAIL address
    is accepted.
    """

    member_address: Annotated[str, AfterValidator(validate_mail_address)]


#
# Query parameters
#
class BoxFilterParams(BaseModel):
    """
    Query parameters for "GET box" endpoints (i.e. inbox, outbox, trash).
    """

    model_config = {"extra": "forbid"}

    limit: int = Field(20, gt=0, le=100)
    offset: int = Field(0, ge=0)
    # sent_at: timestamp when the MAIL message was sent
    # entered_at: timestamp when the message entered the user's box
    sort_by: Literal["sent_at", "entered_at"] = "entered_at"
    # asc: ascending
    # desc: descending
    order: Literal["asc", "desc"] = "desc"
