# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.validators import (
    validate_mail_address,
    validate_message_body,
    validate_message_subject,
    validate_swarm_name,
    validate_url,
    validate_webhook_event_types,
    validate_webhook_id,
    validate_webhook_message_id,
)

MAILWebhookEventType = Literal["mail.delivered"]


class MAILWebhook(BaseModel):
    """
    Object representing a MAIL webhook.
    """

    webhook_id: Annotated[str, AfterValidator(validate_webhook_id)]
    url: Annotated[str, AfterValidator(validate_url)]
    events: Annotated[list[str], AfterValidator(validate_webhook_event_types)]
    secret: str


class MAILMessageInWebhook(BaseModel):
    """
    A MAIL message contained inside a server-sent webhook payload.
    """

    message_id: Annotated[str, AfterValidator(validate_webhook_message_id)]
    sender: Annotated[str, AfterValidator(validate_mail_address)]
    recipient: Annotated[str, AfterValidator(validate_mail_address)]
    subject: Annotated[str, AfterValidator(validate_message_subject)]
    body: Annotated[str, AfterValidator(validate_message_body)]
    sent_at: datetime
    swarm: Annotated[str, AfterValidator(validate_swarm_name)]
    metadata: dict[str, Any]
