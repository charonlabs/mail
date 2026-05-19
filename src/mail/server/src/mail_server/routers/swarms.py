# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter

router = APIRouter(prefix="/swarms", tags=["swarms"])


@router.get("/")
async def get_swarms():
    return {"message": "Hello from GET /swarms!"}


@router.get("/{swarm_name}")
async def get_swarm(swarm_name: str):
    return {"message": f"Hello from GET /swarms/{swarm_name}!"}


@router.get("/{swarm_name}/health")
async def get_swarm_health(swarm_name: str):
    return {"message": f"Hello from GET /swarms/{swarm_name}/health!"}
