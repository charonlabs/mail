# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MAILMessageSummary(BaseModel):
    """
    A summarized MAIL message to be included in lists.
    """

    message_id: str
    sender: str
    recipients: list[str]
    subject: str
    body_size: int
    sent_at: datetime


class MAILMessage(BaseModel):
    """
    A constructed message to be delivered via MAIL.
    """

    message_id: str
    sender: str
    recipients: list[str]
    subject: str
    body: str
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
