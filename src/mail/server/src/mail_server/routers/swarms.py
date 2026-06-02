# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import (
    GetSwarmHealthResponse,
    GetSwarmReadmeResponse,
    GetSwarmResponse,
    GetSwarmsResponse,
)

router = APIRouter(prefix="/swarms", tags=["swarms"])


@router.get(
    "/",
    summary="Get basic server information and metadata",
    response_model=GetSwarmsResponse,
)
async def get_swarms(request: Request) -> GetSwarmsResponse:
    backend = request.app.state.backend
    result = await backend.get_swarms()

    return GetSwarmsResponse(
        swarms=result,
        metadata={},
    )


@router.get(
    "/{swarm_name}",
    summary="Get information on a specific swarm by name",
    response_model=GetSwarmResponse,
)
async def get_swarm(request: Request) -> GetSwarmResponse:
    backend = request.app.state.backend
    swarm_name = request.path_params.get("swarm_name")
    try:
        result = await backend.get_swarm(swarm_name=swarm_name)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"swarm with name {swarm_name} not found"
        )

    return GetSwarmResponse(
        swarm=result,
        metadata={},
    )


@router.get(
    "/{swarm_name}/health",
    summary="Get health information on a specific swarm by name",
    response_model=GetSwarmHealthResponse,
)
async def get_swarm_health(request: Request) -> GetSwarmHealthResponse:
    backend = request.app.state.backend
    swarm_name = request.path_params.get("swarm_name")
    try:
        result = await backend.get_swarm_health(swarm_name=swarm_name)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"swarm with name {swarm_name} not found"
        )

    return GetSwarmHealthResponse(status="ok")
