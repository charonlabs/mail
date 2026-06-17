# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.validators import (
    validate_mail_address,
    validate_message_body,
    validate_message_recipients,
    validate_message_subject,
    validate_message_tags,
    validate_uuid,
)


class MAILMessageSummary(BaseModel):
    """
    A summarized MAIL message to be included in lists.
    """

    message_id: Annotated[str, AfterValidator(validate_uuid)]
    sender: Annotated[str, AfterValidator(validate_mail_address)]
    recipients: Annotated[list[str], AfterValidator(validate_message_recipients)]
    subject: Annotated[str, AfterValidator(validate_message_subject)]
    body_size: int
    sent_at: datetime


class MAILMessage(BaseModel):
    """
    A constructed message to be delivered via MAIL.
    """

    mail_version: Literal["2.0"]
    message_id: Annotated[str, AfterValidator(validate_uuid)]
    reply_to: Annotated[str, AfterValidator(validate_uuid)] | None = None
    sender: Annotated[str, AfterValidator(validate_mail_address)]
    recipients: Annotated[list[str], AfterValidator(validate_message_recipients)]
    subject: Annotated[str, AfterValidator(validate_message_subject)]
    body: Annotated[str, AfterValidator(validate_message_body)]
    tags: Annotated[list[str], AfterValidator(validate_message_tags)]
    sent_at: datetime
    metadata: dict[str, Any]

    def summarize(self) -> MAILMessageSummary:
        """
        Create a summary of this MAIL message.
        """

        body_size = len(self.body)
        return MAILMessageSummary(
            message_id=self.message_id,
            sender=self.sender,
            recipients=self.recipients,
            subject=self.subject,
            body_size=body_size,
            sent_at=self.sent_at,
        )
