# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.network.responses import (
    DeleteAdminAgentResponse,
    DeleteAdminDaemonResponse,
    DeleteAdminUserResponse,
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
    try:
        result = await backend.admin_get_agent(admin=admin, agent_address=agent_address)
    except ValueError:
        raise HTTPException(status_code=404, detail="agent not found")
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
    try:
        result = await backend.admin_post_agent(admin=admin, payload=payload)
    except ValueError:
        raise HTTPException(status_code=409, detail="agent address already taken")
    return PostAdminAgentResponse(
        agent=result,
        metadata={},
    )


@router.delete(
    "/agents/{agent_address}",
    summary="Delete an existing MAIL agent on this server",
    response_model=DeleteAdminAgentResponse,
)
async def delete_agent(
    request: Request,
) -> DeleteAdminAgentResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    agent_address = request.path_params.get("agent_address")
    try:
        result = await backend.admin_delete_agent(
            admin=admin, agent_address=agent_address
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="agent not found")
    return DeleteAdminAgentResponse(
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
    try:
        result = await backend.admin_get_daemon(admin=admin, worker_name=worker_name)
    except ValueError:
        raise HTTPException(status_code=404, detail="daemon not found")
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
    try:
        result = await backend.admin_post_daemon(admin=admin, payload=payload)
    except ValueError:
        raise HTTPException(status_code=409, detail="daemon address already taken")
    return PostAdminDaemonResponse(
        daemon=result,
        metadata={},
    )


@router.delete(
    "/daemons/{worker_name}",
    summary="Delete an existing MAIL daemon on this server",
    response_model=DeleteAdminAgentResponse,
)
async def delete_daemon(
    request: Request,
) -> DeleteAdminDaemonResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    worker_name = request.path_params.get("worker_name")
    try:
        result = await backend.admin_delete_daemon(admin=admin, worker_name=worker_name)
    except ValueError:
        raise HTTPException(status_code=404, detail="daemon not found")
    return DeleteAdminDaemonResponse(
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
    try:
        result = await backend.admin_get_user(admin=admin, user_id=user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="user not found")
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
    try:
        result = await backend.admin_post_user(admin=admin, payload=payload)
    except ValueError:
        raise HTTPException(status_code=409, detail="user address already taken")
    return PostAdminUserResponse(
        user=result,
        metadata={},
    )


@router.delete(
    "/users/{user_id}",
    summary="Delete an existing MAIL user on this server",
    response_model=DeleteAdminUserResponse,
)
async def delete_user(
    request: Request,
) -> DeleteAdminUserResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    user_id = request.path_params.get("user_id")
    try:
        result = await backend.admin_delete_user(admin=admin, user_id=user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="user not found")
    return DeleteAdminUserResponse(
        user=result,
        metadata={},
    )
