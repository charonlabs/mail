# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Annotated

from pydantic import AfterValidator, BaseModel

from mail_protocol.metadata import Metadata


def validate_swarm_name(name: str) -> str:
    """
    Validate the swarm name (must be a non-empty string).
    """
    if len(name) < 1:
        raise ValueError(f"Invalid swarm name: {name}")
    return name


def validate_agents(agents: list[str]) -> list[str]:
    """
    Validate the agents (must be a non-empty list of strings).
    """
    if len(agents) < 1:
        raise ValueError(f"must have at least one agent, got {len(agents)}")
    for agent in agents:
        if len(agent) < 1:
            raise ValueError(f"Invalid agent: {agent}")
    return agents


def validate_entrypoints(entrypoints: list[str]) -> list[str]:
    """
    Validate the entrypoints (must be a non-empty list of strings).
    """
    if len(entrypoints) < 1:
        raise ValueError(f"must have at least one entrypoint, got {len(entrypoints)}")
    for entrypoint in entrypoints:
        if len(entrypoint) < 1:
            raise ValueError(f"Invalid entrypoint: {entrypoint}")
    return entrypoints


def validate_keywords(keywords: list[str]) -> list[str]:
    """
    Validate the keywords (must be a non-empty list of strings).
    """
    if len(keywords) < 1:
        raise ValueError(f"must have at least one keyword, got {len(keywords)}")
    return keywords


def validate_description(description: str | None) -> str | None:
    """
    Validate the description (must be a string).
    """
    if description is not None and len(description) < 1:
        raise ValueError(f"Invalid description: {description}")
    return description


class MAILSwarm(BaseModel):
    """
    The core data model for a local MAIL swarm.
    """
    name: Annotated[str, AfterValidator(validate_swarm_name)]
    agents: Annotated[list[str], AfterValidator(validate_agents)]
    entrypoints: Annotated[list[str], AfterValidator(validate_entrypoints)]
    keywords: Annotated[list[str], AfterValidator(validate_keywords)]
    description: Annotated[str | None, AfterValidator(validate_description)]
    metadata: Metadata