# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.validators import (
    validate_mail_address,
    validate_message_subject,
    validate_uuid,
)


class MAILInboxEntrySummary(BaseModel):
    """
    A summarized MAIL inbox entry to be included in lists.
    """

    message_id: Annotated[str, AfterValidator(validate_uuid)]
    sender: Annotated[str, AfterValidator(validate_mail_address)]
    subject: Annotated[str, AfterValidator(validate_message_subject)]
    body_size: int
    received_at: datetime
    delivered_by: Annotated[str, AfterValidator(validate_mail_address)]


class MAILInboxEntry(BaseModel):
    """
    Wrapper for an individual MAIL message in a user-agent's inbox.
    """

    message: MAILMessage
    received_at: datetime
    delivered_by: Annotated[str, AfterValidator(validate_mail_address)]

    def summarize(self) -> MAILInboxEntrySummary:
        """
        Create a summary of this inbox entry.
        """

        body_size = len(self.message.body)
        return MAILInboxEntrySummary(
            message_id=self.message.message_id,
            sender=self.message.sender,
            subject=self.message.subject,
            body_size=body_size,
            received_at=self.received_at,
            delivered_by=self.delivered_by,
        )
