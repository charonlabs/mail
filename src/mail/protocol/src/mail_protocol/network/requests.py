# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from pydantic import BaseModel

from mail_protocol.core.messages import MAILMessage


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
    Contains relevant information for creating a new MAIL message draft.
    """

    subject: str
    body: str


class PostDraftSendRequest(BaseModel):
    """
    Contains relevant information for sending an existing draft as a MAIL message.
    """

    recipients: list[str]


#
# Trash endpoints
#
class PostTrashClearRequest(BaseModel):
    """
    No body for this endpoint yet.
    """

    pass


#
# Daemon endpoints
#
class PostDaemonDeliverLocalRequest(BaseModel):
    """
    Contains a list of local message IDs to deliver to their intended local targets.
    """

    message_ids: list[str]


class PostDaemonDeliverRemoteRequest(BaseModel):
    """
    Contains a list of remote MAIL messages to deliver to their intended local targets.
    """

    messages: list[MAILMessage]
