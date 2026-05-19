# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from datetime import datetime

from pydantic import BaseModel

from mail_protocol.core.messages import MAILMessage


class MAILQueueEntrySummary(BaseModel):
    """
    A summarized MAIL message queue entry to be included in lists.
    """

    message_id: str
    sender: str
    recipients: list[str]
    subject: str
    body_size: int
    queued_at: datetime


class MAILQueueEntry(BaseModel):
    """
    Wrapper for an invidual MAIL message in the server delivery queue.
    """

    message: MAILMessage
    queued_at: datetime

    def summarize(self) -> MAILQueueEntrySummary:
        """
        Create a summary of this message queue entry.
        """

        body_size = len(self.message.body)
        return MAILQueueEntrySummary(
            message_id=self.message.message_id,
            sender=self.message.sender,
            recipients=self.message.recipients,
            subject=self.message.subject,
            body_size=body_size,
            queued_at=self.queued_at,
        )
