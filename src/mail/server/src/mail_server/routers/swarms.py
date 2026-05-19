# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter
from mail_protocol.network.responses import (
    GetSwarmHealthResponse,
    GetSwarmResponse,
    GetSwarmsResponse,
)

router = APIRouter(prefix="/swarms", tags=["swarms"])


@router.get(
    "/",
    summary="Get basic server information and metadata",
    response_model=GetSwarmsResponse,
)
async def get_swarms() -> GetSwarmsResponse:
    raise NotImplementedError


@router.get(
    "/{swarm_name}",
    summary="Get information on a specific swarm by name",
    response_model=GetSwarmResponse,
)
async def get_swarm(swarm_name: str) -> GetSwarmResponse:
    raise NotImplementedError


@router.get(
    "/{swarm_name}/health",
    summary="Get health information on a specific swarm by name",
    response_model=GetSwarmHealthResponse,
)
async def get_swarm_health(swarm_name: str) -> GetSwarmHealthResponse:
    raise NotImplementedError
