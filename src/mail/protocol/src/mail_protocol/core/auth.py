# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.validators import validate_mail_address


class RefreshTokenRecord(BaseModel):
    """
    A stored refresh token, as persisted by a MAIL server backend.

    Backend-internal — this never crosses the wire. The plaintext token is
    returned to the client exactly once at issuance; only its SHA-256 hash is
    stored, so this record carries the hash rather than the token itself.

    Refresh tokens are grouped into *families*: the token minted at login starts
    a family, and every rotation keeps the same ``family_id``. ``expires_at`` is
    an absolute cap set at login and carried forward unchanged on rotation (it
    does not slide). A token is unusable once ``revoked`` is ``True`` or
    ``rotated_at`` is set — presenting such a token is treated as reuse and
    revokes the whole family.
    """

    token_hash: str
    family_id: str
    owner_address: Annotated[str, AfterValidator(validate_mail_address)]
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False
    rotated_at: datetime | None = None
