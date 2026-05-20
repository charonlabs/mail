# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from typing import Annotated, Literal, Union

from pydantic import AfterValidator, BaseModel, Field

from mail_protocol.core.validators import (
    validate_agent_name,
    validate_daemon_worker_name,
    validate_host,
    validate_swarm_name,
    validate_uuid,
)


class MAILAgent(BaseModel):
    ua_type: Literal["agent"]
    name: Annotated[str, AfterValidator(validate_agent_name)]
    swarm: Annotated[str, AfterValidator(validate_swarm_name)]
    host: Annotated[str, AfterValidator(validate_host)]


class MAILUser(BaseModel):
    ua_type: Literal["user"]
    user_id: Annotated[str, AfterValidator(validate_uuid)]
    host: Annotated[str, AfterValidator(validate_host)]


class MAILAdmin(BaseModel):
    ua_type: Literal["admin"]
    admin_id: Annotated[str, AfterValidator(validate_uuid)]
    host: Annotated[str, AfterValidator(validate_host)]


class MAILDaemon(BaseModel):
    ua_type: Literal["daemon"]
    worker_name: Annotated[str, AfterValidator(validate_daemon_worker_name)]
    host: Annotated[str, AfterValidator(validate_host)]


class MAILUserAgent(BaseModel):
    """
    Base class for MAIL user-agents.
    """

    user_agent: Union[MAILAgent, MAILUser, MAILAdmin, MAILDaemon] = Field(
        discriminator="ua_type"
    )

    def get_address(self) -> str:
        """
        Dump the user-agent to a MAIL address string.
        """

        match self.user_agent:
            case MAILAgent():
                agent_name = self.user_agent.name
                swarm_name = self.user_agent.swarm
                host = self.user_agent.host
                return f"{agent_name}@{swarm_name}@{host}"
            case MAILUser():
                user_id = self.user_agent.user_id
                host = self.user_agent.host
                return f"user:{user_id}@{host}"
            case MAILAdmin():
                admin_id = self.user_agent.admin_id
                host = self.user_agent.host
                return f"admin:{admin_id}@{host}"
            case MAILDaemon():
                worker_name = self.user_agent.worker_name
                host = self.user_agent.host
                return f"daemon:{worker_name}@{host}"


class MAILUserAgentInBackend(MAILUserAgent):
    hashed_password: str
