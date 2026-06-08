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


class MAILTrashEntrySummary(BaseModel):
    """
    A summarized MAIL trash entry to be included in lists.
    """

    message_id: Annotated[str, AfterValidator(validate_uuid)]
    sender: Annotated[str, AfterValidator(validate_mail_address)]
    subject: Annotated[str, AfterValidator(validate_message_subject)]
    body_size: int
    trashed_at: datetime


class MAILTrashEntry(BaseModel):
    """
    Wrapper for an individual MAIL message in a user-agent's trash box.
    """

    message: MAILMessage
    trashed_at: datetime

    def summarize(self) -> MAILTrashEntrySummary:
        """
        Create a summary of this trash entry.
        """

        body_size = len(self.message.body)
        return MAILTrashEntrySummary(
            message_id=self.message.message_id,
            sender=self.message.sender,
            subject=self.message.subject,
            body_size=body_size,
            trashed_at=self.trashed_at,
        )
