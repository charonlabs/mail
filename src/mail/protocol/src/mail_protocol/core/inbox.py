# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from datetime import datetime

from pydantic import BaseModel

from mail_protocol.core.messages import MAILMessage


class MAILInboxEntrySummary(BaseModel):
    """
    A summarized MAIL inbox entry to be included in lists.
    """

    message_id: str
    sender: str
    subject: str
    body_size: int
    received_at: datetime
    opened: bool


class MAILInboxEntry(BaseModel):
    """
    Wrapper for an individual MAIL message in a user-agent's inbox.
    """

    message: MAILMessage
    received_at: datetime
    opened: bool

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
            opened=self.opened,
        )
