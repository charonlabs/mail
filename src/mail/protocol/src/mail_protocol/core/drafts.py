# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.validators import (
    validate_mail_address,
    validate_message_body,
    validate_message_subject,
    validate_uuid,
)


class MAILDraft(BaseModel):
    """
    A draft of an individual MAIL message.
    Does not yet account for intended recipients.
    """

    draft_id: Annotated[str, AfterValidator(validate_uuid)]
    subject: Annotated[str, AfterValidator(validate_message_subject)]
    body: Annotated[str, AfterValidator(validate_message_body)]
    created_at: datetime
    updated_at: datetime | None = None


class MAILDraftsEntrySummary(BaseModel):
    """
    A summarized MAIL draft entry to be included in lists.
    """

    draft_id: Annotated[str, AfterValidator(validate_uuid)]
    subject: Annotated[str, AfterValidator(validate_message_subject)]
    body_size: int
    created_at: datetime
    updated_at: datetime | None = None


class MAILDraftsEntry(BaseModel):
    """
    A MAIL message draft in a user-agent's drafts box.
    """

    draft: MAILDraft
    sent_at: datetime | None = None
    sent_by: Annotated[str, AfterValidator(validate_mail_address)] | None = None

    def summarize(self) -> MAILDraftsEntrySummary:
        """
        Create a summary of this draft entry.
        """

        body_size = len(self.draft.body)
        return MAILDraftsEntrySummary(
            draft_id=self.draft.draft_id,
            subject=self.draft.subject,
            body_size=body_size,
            created_at=self.draft.created_at,
            updated_at=self.draft.updated_at,
        )
