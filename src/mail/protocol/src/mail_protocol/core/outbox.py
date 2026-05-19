# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from datetime import datetime

from pydantic import BaseModel

from mail_protocol.core.messages import MAILMessage


class MAILOutboxEntrySummary(BaseModel):
    """
    A summarized MAIL outbox entry to be included in lists.
    """

    message_id: str
    recipients: list[str]
    subject: str
    body_size: int
    sent_at: datetime
    delivered_at: datetime | None = None


class MAILOutboxEntry(BaseModel):
    """
    Wrapper for an individual MAIL message in a user-agent's outbox.
    """

    message: MAILMessage
    delivered_at: datetime | None = None

    def summarize(self) -> MAILOutboxEntrySummary:
        """
        Create a summary of this outbox entry.
        """

        body_size = len(self.message.body)
        return MAILOutboxEntrySummary(
            message_id=self.message.message_id,
            recipients=self.message.recipients,
            subject=self.message.subject,
            body_size=body_size,
            sent_at=self.message.sent_at,
            delivered_at=self.delivered_at,
        )
