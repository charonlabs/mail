# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import asyncio
import logging

from mail.api import MAILSwarm, MAILSwarmTemplate
from mail.config import ServerConfig
from mail.net.registry import SwarmRegistry

logger = logging.getLogger(__name__)


def compute_external_base_url(cfg: ServerConfig) -> str:
    """
    Derive an externally-reachable base URL from the server config.
    """

    host = cfg.host
    port = cfg.port

    if host in {"0.0.0.0", "::"}:
        # 0.0.0.0/:: listen on all interfaces; default to localhost for callbacks
        host_for_url = "localhost"
    else:
        host_for_url = host

    return f"http://{host_for_url}:{port}"


def get_default_persistent_swarm(
    cfg: ServerConfig,
) -> MAILSwarmTemplate:
    """
    Get the default persistent swarm template from the server config.
    """
    swarm_name = cfg.swarm.name
    swarm_json_file = cfg.swarm.source

    return MAILSwarmTemplate.from_swarm_json_file(
        swarm_name=swarm_name,
        json_filepath=swarm_json_file,
    )


def init_mail_instances_dict() -> dict[str, MAILSwarm]:
    """
    Initialize the mail instances dictionary for a given role.
    Should always be empty on startup.
    """
    return {}


def init_mail_tasks_dict() -> dict[str, asyncio.Task]:
    """
    Initialize the mail tasks dictionary for a given role.
    Should always be empty on startup.
    """
    return {}


def get_default_swarm_registry(
    cfg: ServerConfig, swarm: MAILSwarmTemplate
) -> SwarmRegistry:
    """
    Get the default swarm registry from the server config.
    """
    swarm_name = swarm.name
    swarm_registry_file = cfg.swarm.registry_file
    local_base_url = get_default_base_url(cfg)

    return SwarmRegistry(
        local_swarm_name=swarm_name,
        local_base_url=local_base_url,
        persistence_file=swarm_registry_file,
        local_swarm_description=swarm.description,
        local_swarm_keywords=swarm.keywords,
        local_swarm_public=swarm.public,
    )


def get_default_swarm_name(
    cfg: ServerConfig,
) -> str:
    """
    Get the default swarm name from the server config.
    """
    return cfg.swarm.name


def get_default_base_url(
    cfg: ServerConfig,
) -> str:
    """
    Get the default base URL from the server config.
    """
    return compute_external_base_url(cfg)


def get_default_entrypoint_agent(
    swarm_template: MAILSwarmTemplate,
) -> str:
    """
    Get the default entrypoint agent from the swarm template.
    """
    return swarm_template.entrypoint


def init_task_bindings_dict() -> dict[str, dict[str, str]]:
    """
    Initialize the task bindings dictionary.
    Should always be empty on startup.
    """
    return {}
