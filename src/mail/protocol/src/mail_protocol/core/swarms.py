# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel

from mail_protocol.core.validators import (
    validate_agent_names,
    validate_swarm_description,
    validate_swarm_keywords,
    validate_swarm_name,
)


class MAILSwarmSummary(BaseModel):
    """
    More concise summary of a MAIL swarm.
    """

    name: Annotated[str, AfterValidator(validate_swarm_name)]
    description: Annotated[str, AfterValidator(validate_swarm_description)]
    keywords: Annotated[list[str], AfterValidator(validate_swarm_keywords)]
    num_agents: int


class MAILSwarm(BaseModel):
    """
    Abstract MAIL swarm class.
    """

    name: Annotated[str, AfterValidator(validate_swarm_name)]
    description: Annotated[str, AfterValidator(validate_swarm_description)]
    keywords: Annotated[list[str], AfterValidator(validate_swarm_keywords)]
    agents: Annotated[list[str], AfterValidator(validate_agent_names)]
    metadata: dict[str, Any]

    def summarize(self) -> MAILSwarmSummary:
        """
        Create a summary of this MAIL swarm.
        """

        num_agents = len(self.agents)
        return MAILSwarmSummary(
            name=self.name,
            description=self.description,
            keywords=self.keywords,
            num_agents=num_agents,
        )
