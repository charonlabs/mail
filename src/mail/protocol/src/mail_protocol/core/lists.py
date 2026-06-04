# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field

from mail_protocol.core.validators import (
    validate_host,
    validate_list_name,
    validate_mail_address,
    validate_mail_addresses,
    validate_swarm_name,
    validate_uuid,
)


class MAILListPolicy(BaseModel):
    """
    Policy controls for a MAIL list.

    All three fields are forward-looking — the wire format reserves the
    enumerations now so future contributions can extend ``join_policy``
    and ``send_policy`` without changing the protocol shape.

    For v1 contribution scope, only the ``public`` / ``open`` / ``open``
    variants are honored by the server. Other variants validate at the
    protocol layer but are rejected at the endpoint layer.
    """

    visibility: Literal["public", "private"] = "public"
    join_policy: Literal["open", "approval", "admin-only"] = "open"
    send_policy: Literal["open", "members-only", "admin-only"] = "open"


class MAILList(BaseModel):
    """
    A MAIL mailing list — a swarm-scoped, addressable fan-out target.

    Sending mail with ``list:<name>@<swarm>@<host>`` in the recipient
    field causes MAIL's local delivery path to expand the list and
    deliver one copy of the message to each member. The list address
    itself does not own an inbox.
    """

    list_type: Literal["list"] = "list"
    name: Annotated[str, AfterValidator(validate_list_name)]
    swarm: Annotated[str, AfterValidator(validate_swarm_name)]
    host: Annotated[str, AfterValidator(validate_host)]
    owner: Annotated[str, AfterValidator(validate_mail_address)]
    members: Annotated[list[str], AfterValidator(validate_mail_addresses)] = Field(
        default_factory=list
    )
    policy: MAILListPolicy = Field(default_factory=MAILListPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_address(self) -> str:
        """
        Dump the list to a MAIL address string.
        """

        return f"list:{self.name}@{self.swarm}@{self.host}"


class MAILListInBackend(MAILList):
    """
    Backend storage variant — adds the assigned id and timestamps.
    """

    list_id: Annotated[str, AfterValidator(validate_uuid)]
    created_at: datetime
    updated_at: datetime
