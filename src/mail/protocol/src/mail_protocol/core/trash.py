# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from datetime import datetime

from pydantic import BaseModel

from mail_protocol.core.messages import MAILMessage


class MAILTrashEntrySummary(BaseModel):
    """
    A summarized MAIL trash entry to be included in lists.
    """

    message_id: str
    sender: str
    subject: str
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
