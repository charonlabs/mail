# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

from pydantic import BaseModel


class MAILInterswarmAttachment(BaseModel):
    """
    A MAIL interswarm attachment.
    """
    attachment_name: str
    attachment_type: str
    attachment_data: str
    metadata: dict[str, Any]