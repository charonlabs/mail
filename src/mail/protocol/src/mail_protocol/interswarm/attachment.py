# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import mimetypes
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel


def validate_attachment_name(attachment_name: str) -> str:
    """
    Validate a MAIL interswarm attachment name.
    """
    if not attachment_name.strip():
        raise ValueError(f"Invalid MAIL interswarm attachment name: {attachment_name}")
    return attachment_name


def validate_mime_type(mime_type: str) -> str:
    """
    Validate a MIME type string.
    """
    if not mimetypes.guess_type(mime_type)[0]:
        raise ValueError(f"Invalid MIME type: {mime_type}")
    return mime_type


def validate_base64(base64: str) -> str:
    """
    Validate a base64 string.
    """
    if not base64.strip():
        raise ValueError(f"Invalid base64: {base64}")
    return base64


class MAILInterswarmAttachment(BaseModel):
    """
    A MAIL interswarm attachment.
    """
    attachment_name: Annotated[str, AfterValidator(validate_attachment_name)]
    attachment_type: Annotated[str, AfterValidator(validate_mime_type)]
    attachment_data: Annotated[str, AfterValidator(validate_base64)]
    metadata: dict[str, Any]