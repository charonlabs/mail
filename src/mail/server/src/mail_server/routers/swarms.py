# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import (
    SwarmGetResponse,
    SwarmHealthGetResponse,
    SwarmsGetResponse,
)

router = APIRouter(prefix="/swarms", tags=["swarms"])


@router.get(
    "/",
    summary="Get basic server information and metadata",
    response_model=SwarmsGetResponse,
)
async def get_swarms(request: Request) -> SwarmsGetResponse:
    backend = request.app.state.backend
    result = await backend.get_swarms()

    return SwarmsGetResponse(
        swarms=result,
        metadata={},
    )


@router.get(
    "/{swarm_name}",
    summary="Get information on a specific swarm by name",
    response_model=SwarmGetResponse,
)
async def get_swarm(request: Request) -> SwarmGetResponse:
    backend = request.app.state.backend
    swarm_name = request.path_params.get("swarm_name")
    try:
        result = await backend.get_swarm(swarm_name=swarm_name)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"swarm with name {swarm_name} not found"
        )

    return SwarmGetResponse(
        swarm=result,
        metadata={},
    )


@router.get(
    "/{swarm_name}/health",
    summary="Get health information on a specific swarm by name",
    response_model=SwarmHealthGetResponse,
)
async def get_swarm_health(request: Request) -> SwarmHealthGetResponse:
    backend = request.app.state.backend
    swarm_name = request.path_params.get("swarm_name")
    try:
        result = await backend.get_swarm_health(swarm_name=swarm_name)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"swarm with name {swarm_name} not found"
        )

    return SwarmHealthGetResponse(status="ok")
