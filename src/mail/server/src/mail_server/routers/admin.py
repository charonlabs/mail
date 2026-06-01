# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, Request
from mail_protocol.network.responses import (
    GetAdminAgentResponse,
    GetAdminAgentsResponse,
    GetAdminDaemonResponse,
    GetAdminDaemonsResponse,
    GetAdminUserResponse,
    GetAdminUsersResponse,
    PostAdminAgentResponse,
    PostAdminDaemonResponse,
    PostAdminUserResponse,
)

from mail_server.auth import validate_admin
from mail_server.validators import (
    validate_admin_post_agent_request,
    validate_admin_post_daemon_request,
    validate_admin_post_user_request,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/agents",
    summary="Get a list of agents registered on this server",
    response_model=GetAdminAgentsResponse,
)
async def get_agents(
    request: Request,
) -> GetAdminAgentsResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    result = await backend.admin_get_agents(admin=admin)
    return GetAdminAgentsResponse(
        agents=result,
        metadata={},
    )


@router.get(
    "/agents/{agent_address}",
    summary="Get a specific registered agent by local address (name@swarm)",
    response_model=GetAdminAgentResponse,
)
async def get_agent(
    request: Request,
) -> GetAdminAgentResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    agent_address = request.path_params.get("agent_address")
    result = await backend.admin_get_agent(admin=admin, agent_address=agent_address)
    return GetAdminAgentResponse(
        agent=result,
        metadata={},
    )


@router.post(
    "/agents",
    summary="Create a new MAIL agent on this server",
    response_model=PostAdminAgentResponse,
)
async def post_agent(
    request: Request,
) -> PostAdminAgentResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_post_agent_request(request=request)
    result = await backend.admin_post_agent(admin=admin, payload=payload)
    return PostAdminAgentResponse(
        agent=result,
        metadata={},
    )


@router.get(
    "/daemons",
    summary="Get a list of daemons registered on this server",
    response_model=GetAdminDaemonsResponse,
)
async def get_daemons(
    request: Request,
) -> GetAdminDaemonsResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    result = await backend.admin_get_daemons(admin=admin)
    return GetAdminDaemonsResponse(
        daemons=result,
        metadata={},
    )


@router.get(
    "/daemons/{worker_name}",
    summary="Get a specific registered daemon by worker name",
    response_model=GetAdminDaemonResponse,
)
async def get_daemon(
    request: Request,
) -> GetAdminDaemonResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    worker_name = request.path_params.get("worker_name")
    result = await backend.admin_get_daemon(admin=admin, worker_name=worker_name)
    return GetAdminDaemonResponse(
        daemon=result,
        metadata={},
    )


@router.post(
    "/daemons",
    summary="Create a new MAIL daemon on this server",
    response_model=PostAdminDaemonResponse,
)
async def post_daemon(
    request: Request,
) -> PostAdminDaemonResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_post_daemon_request(request=request)
    result = await backend.admin_post_daemon(admin=admin, payload=payload)
    return PostAdminDaemonResponse(
        daemon=result,
        metadata={},
    )


@router.get(
    "/users",
    summary="Get a list of users registered on this server",
    response_model=GetAdminUsersResponse,
)
async def get_users(
    request: Request,
) -> GetAdminUsersResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    result = await backend.admin_get_users(admin=admin)
    return GetAdminUsersResponse(
        users=result,
        metadata={},
    )


@router.get(
    "/users/{user_id}",
    summary="Get a specific registered user by ID",
    response_model=GetAdminUserResponse,
)
async def get_user(
    request: Request,
) -> GetAdminUserResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    user_id = request.path_params.get("user_id")
    result = await backend.admin_get_user(admin=admin, user_id=user_id)
    return GetAdminUserResponse(
        user=result,
        metadata={},
    )


@router.post(
    "/users",
    summary="Create a new MAIL user on this server",
    response_model=PostAdminUserResponse,
)
async def post_user(
    request: Request,
) -> PostAdminUserResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_post_user_request(request=request)
    result = await backend.admin_post_user(admin=admin, payload=payload)
    return PostAdminUserResponse(
        user=result,
        metadata={},
    )
