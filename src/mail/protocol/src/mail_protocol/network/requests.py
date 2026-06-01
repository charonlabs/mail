# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from typing import Annotated

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.validators import (
    validate_agent_name,
    validate_daemon_worker_name,
    validate_mail_addresses,
    validate_message_body,
    validate_message_subject,
    validate_swarm_name,
    validate_user_name,
    validate_uuids,
)


#
# Authentication endpoints
#
class PostAuthTokenRequest(BaseModel):
    """
    Submit valid credentials to obtain a JWT for subsequent use.
    """

    pass


#
# Draft endpoints
#
class PostDraftRequest(BaseModel):
    """
    Corresponds to `POST /drafts/`.
    Contains relevant information for creating a new MAIL message draft.
    """

    subject: Annotated[str, AfterValidator(validate_message_subject)]
    body: Annotated[str, AfterValidator(validate_message_body)]


class PostDraftSendRequest(BaseModel):
    """
    Corresponds to `POST /drafts/{draft_id}/send`.
    Contains relevant information for sending an existing draft as a MAIL message.
    """

    recipients: Annotated[list[str], AfterValidator(validate_mail_addresses)]


#
# Trash endpoints
#
class PostTrashClearRequest(BaseModel):
    """
    Corresponds to `POST /trash/clear`.
    No body for this endpoint.
    """

    pass


#
# Daemon endpoints
#
class PostDaemonDeliverLocalRequest(BaseModel):
    """
    Corresponds to `POST /daemon/deliver/local`.
    Contains a list of local message IDs to deliver to their intended local targets.
    """

    message_ids: Annotated[list[str], AfterValidator(validate_uuids)]


class PostDaemonDeliverRemoteRequest(BaseModel):
    """
    Corresponds to `POST /daemon/deliver/remote`.
    Contains a list of remote MAIL messages to deliver to their intended local targets.
    """

    messages: list[MAILMessage]


#
# Administrator endpoints
#
class PostAdminAgentRequest(BaseModel):
    """
    Corresponds to `POST /admin/agents`.
    Contains an agent name, swarm, and password to register with.
    """

    agent_name: Annotated[str, AfterValidator(validate_agent_name)]
    swarm_name: Annotated[str, AfterValidator(validate_swarm_name)]
    agent_password: str


class PostAdminDaemonRequest(BaseModel):
    """
    Corresponds to `POST /admin/daemons`.
    Contains a worker name and password to register with.
    """

    worker_name: Annotated[str, AfterValidator(validate_daemon_worker_name)]
    daemon_password: str


class PostAdminUserRequest(BaseModel):
    """
    Corresponds to `POST /admin/users`.
    Contains a user ID and password to register with.
    """

    user_id: Annotated[str, AfterValidator(validate_user_name)]
    user_password: str
