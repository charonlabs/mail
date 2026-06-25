# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter, HTTPException, Path, Request
from mail_protocol.network.responses import (
    AdminAgentDeleteResponse,
    AdminAgentGetResponse,
    AdminAgentPostResponse,
    AdminAgentsGetResponse,
    AdminDaemonDeleteResponse,
    AdminDaemonGetResponse,
    AdminDaemonPostResponse,
    AdminDaemonsGetResponse,
    AdminSwarmDeleteResponse,
    AdminSwarmPostResponse,
    AdminUserDeleteResponse,
    AdminUserGetResponse,
    AdminUserPostResponse,
    AdminUsersGetResponse,
    AdminWebhookGetResponse,
    AdminWebhooksDeleteResponse,
    AdminWebhooksGetResponse,
    AdminWebhooksPatchResponse,
    AdminWebhooksPostResponse,
)

from mail_server.auth import validate_admin
from mail_server.validators import (
    validate_admin_post_agent_request,
    validate_admin_post_daemon_request,
    validate_admin_post_swarm_request,
    validate_admin_post_user_request,
    validate_admin_webhook_patch_request,
    validate_admin_webhook_post_request,
    validate_local_address_param,
    validate_swarm_name_param,
    validate_user_id_param,
    validate_webhook_id_param,
    validate_worker_name_param,
)

router = APIRouter(prefix="/admin", tags=["admin"])


#
# Agent endpoints
#
@router.get(
    "/agents",
    summary="Get a list of agents registered on this server",
    response_model=AdminAgentsGetResponse,
)
async def get_agents(
    request: Request,
) -> AdminAgentsGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    result = await backend.admin_get_agents(admin=admin)

    return AdminAgentsGetResponse(
        agents=result,
        metadata={},
    )


@router.get(
    "/agents/{local_address}",
    summary="Get a specific registered agent by local address (name@swarm)",
    response_model=AdminAgentGetResponse,
)
async def get_agent(
    request: Request,
    local_address: str = Path(
        description="Agent local address (name@swarm); host is implied.",
        examples=["researcher@acme"],
    ),
) -> AdminAgentGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    local_address = validate_local_address_param(local_address)
    try:
        result = await backend.admin_get_agent(admin=admin, local_address=local_address)
    except ValueError:
        raise HTTPException(status_code=404, detail="agent not found")

    return AdminAgentGetResponse(
        agent=result,
        metadata={},
    )


@router.post(
    "/agents",
    summary="Create a new MAIL agent on this server",
    response_model=AdminAgentPostResponse,
)
async def post_agent(
    request: Request,
) -> AdminAgentPostResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_post_agent_request(request=request)
    try:
        result = await backend.admin_post_agent(admin=admin, payload=payload)
    except ValueError:
        raise HTTPException(status_code=409, detail="agent address already taken")

    return AdminAgentPostResponse(
        agent=result,
        metadata={},
    )


@router.delete(
    "/agents/{local_address}",
    summary="Delete an existing MAIL agent on this server",
    response_model=AdminAgentDeleteResponse,
)
async def delete_agent(
    request: Request,
    local_address: str = Path(
        description="Agent local address (name@swarm); host is implied.",
        examples=["researcher@acme"],
    ),
) -> AdminAgentDeleteResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    local_address = validate_local_address_param(local_address)
    try:
        result = await backend.admin_delete_agent(
            admin=admin, local_address=local_address
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="agent not found")

    return AdminAgentDeleteResponse(
        agent=result,
        metadata={},
    )


#
# Daemon endpoints
#
@router.get(
    "/daemons",
    summary="Get a list of daemons registered on this server",
    response_model=AdminDaemonsGetResponse,
)
async def get_daemons(
    request: Request,
) -> AdminDaemonsGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    result = await backend.admin_get_daemons(admin=admin)

    return AdminDaemonsGetResponse(
        daemons=result,
        metadata={},
    )


@router.get(
    "/daemons/{worker_name}",
    summary="Get a specific registered daemon by worker name",
    response_model=AdminDaemonGetResponse,
)
async def get_daemon(
    request: Request,
    worker_name: str = Path(
        description="Daemon worker name; prefix and host are implied.",
        examples=["indexer"],
    ),
) -> AdminDaemonGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    worker_name = validate_worker_name_param(worker_name)
    try:
        result = await backend.admin_get_daemon(admin=admin, worker_name=worker_name)
    except ValueError:
        raise HTTPException(status_code=404, detail="daemon not found")

    return AdminDaemonGetResponse(
        daemon=result,
        metadata={},
    )


@router.post(
    "/daemons",
    summary="Create a new MAIL daemon on this server",
    response_model=AdminDaemonPostResponse,
)
async def post_daemon(
    request: Request,
) -> AdminDaemonPostResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_post_daemon_request(request=request)
    try:
        result = await backend.admin_post_daemon(admin=admin, payload=payload)
    except ValueError:
        raise HTTPException(status_code=409, detail="daemon address already taken")

    return AdminDaemonPostResponse(
        daemon=result,
        metadata={},
    )


@router.delete(
    "/daemons/{worker_name}",
    summary="Delete an existing MAIL daemon on this server",
    response_model=AdminDaemonDeleteResponse,
)
async def delete_daemon(
    request: Request,
    worker_name: str = Path(
        description="Daemon worker name; prefix and host are implied.",
        examples=["indexer"],
    ),
) -> AdminDaemonDeleteResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    worker_name = validate_worker_name_param(worker_name)
    try:
        result = await backend.admin_delete_daemon(admin=admin, worker_name=worker_name)
    except ValueError:
        raise HTTPException(status_code=404, detail="daemon not found")

    return AdminDaemonDeleteResponse(
        daemon=result,
        metadata={},
    )


#
# User endpoints
#
@router.get(
    "/users",
    summary="Get a list of users registered on this server",
    response_model=AdminUsersGetResponse,
)
async def get_users(
    request: Request,
) -> AdminUsersGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    result = await backend.admin_get_users(admin=admin)

    return AdminUsersGetResponse(
        users=result,
        metadata={},
    )


@router.get(
    "/users/{user_id}",
    summary="Get a specific registered user by ID",
    response_model=AdminUserGetResponse,
)
async def get_user(
    request: Request,
    user_id: str = Path(
        description="User id; prefix and host are implied.",
        examples=["addison"],
    ),
) -> AdminUserGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    user_id = validate_user_id_param(user_id)
    try:
        result = await backend.admin_get_user(admin=admin, user_id=user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="user not found")

    return AdminUserGetResponse(
        user=result,
        metadata={},
    )


@router.post(
    "/users",
    summary="Create a new MAIL user on this server",
    response_model=AdminUserPostResponse,
)
async def post_user(
    request: Request,
) -> AdminUserPostResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_post_user_request(request=request)
    try:
        result = await backend.admin_post_user(admin=admin, payload=payload)
    except ValueError:
        raise HTTPException(status_code=409, detail="user address already taken")

    return AdminUserPostResponse(
        user=result,
        metadata={},
    )


@router.delete(
    "/users/{user_id}",
    summary="Delete an existing MAIL user on this server",
    response_model=AdminUserDeleteResponse,
)
async def delete_user(
    request: Request,
    user_id: str = Path(
        description="User id; prefix and host are implied.",
        examples=["addison"],
    ),
) -> AdminUserDeleteResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    user_id = validate_user_id_param(user_id)
    try:
        result = await backend.admin_delete_user(admin=admin, user_id=user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="user not found")

    return AdminUserDeleteResponse(
        user=result,
        metadata={},
    )


#
# Swarm endpoints
#
@router.post(
    "/swarms",
    summary="Create a new MAIL swarm on this server",
    response_model=AdminSwarmPostResponse,
)
async def post_swarm(request: Request) -> AdminSwarmPostResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_post_swarm_request(request=request)
    try:
        result = await backend.admin_post_swarm(admin=admin, payload=payload)
    except ValueError:
        raise HTTPException(status_code=409, detail="swarm name already taken")

    return AdminSwarmPostResponse(
        swarm=result,
        metadata={},
    )


@router.delete(
    "/swarms/{swarm_name}",
    summary="Delete an existing MAIL swarm on this server by name",
    response_model=AdminSwarmDeleteResponse,
)
async def delete_swarm(
    request: Request,
    swarm_name: str = Path(
        description="Swarm name.",
        examples=["acme"],
    ),
) -> AdminSwarmDeleteResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    swarm_name = validate_swarm_name_param(swarm_name)
    try:
        result = await backend.admin_delete_swarm(admin=admin, swarm_name=swarm_name)
    except ValueError:
        raise HTTPException(status_code=404, detail="swarm not found")

    return AdminSwarmDeleteResponse(
        swarm=result,
        metadata={},
    )


#
# Webhook endpoints
#
@router.get(
    "/webhooks",
    summary="Get the IDs of all existing server webhooks",
    response_model=AdminWebhooksGetResponse,
)
async def get_webhooks(request: Request) -> AdminWebhooksGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    result = await backend.admin_webhooks_get(admin=admin)

    return AdminWebhooksGetResponse(
        webhook_ids=result,
        metadata={},
    )


@router.get(
    "/webhooks/{webhook_id}",
    summary="Get a specific existing server webhook by ID",
    response_model=AdminWebhookGetResponse,
)
async def get_webhook(
    request: Request,
    webhook_id: str = Path(
        description="Webhook id (wh_<uuid>).",
        examples=["wh_123e4567-e89b-12d3-a456-426614174000"],
    ),
) -> AdminWebhookGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    webhook_id = validate_webhook_id_param(webhook_id)
    try:
        result = await backend.admin_webhook_get(admin=admin, webhook_id=webhook_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="webhook not found")

    return AdminWebhookGetResponse(
        webhook=result,
        metadata={},
    )


@router.post(
    "/webhooks",
    summary="Create a new webhook for this server",
    response_model=AdminWebhooksPostResponse,
)
async def post_webhook(request: Request) -> AdminWebhooksPostResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_webhook_post_request(request=request)
    result = await backend.admin_webhook_post(admin=admin, payload=payload)

    return AdminWebhooksPostResponse(
        webhook=result,
        metadata={},
    )


@router.patch(
    "/webhooks/{webhook_id}",
    summary="Update an existing webhook by ID on this server",
    response_model=AdminWebhooksPatchResponse,
)
async def patch_webhook(
    request: Request,
    webhook_id: str = Path(
        description="Webhook id (wh_<uuid>).",
        examples=["wh_123e4567-e89b-12d3-a456-426614174000"],
    ),
) -> AdminWebhooksPatchResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_webhook_patch_request(request=request)
    webhook_id = validate_webhook_id_param(webhook_id)
    try:
        result = await backend.admin_webhook_patch(
            admin=admin, webhook_id=webhook_id, payload=payload
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="webhook not found")

    return AdminWebhooksPatchResponse(
        webhook=result,
        metadata={},
    )


@router.delete(
    "/webhooks/{webhook_id}",
    summary="Delete an existing webhook by ID from this server",
    response_model=AdminWebhooksDeleteResponse,
)
async def delete_webhook(
    request: Request,
    webhook_id: str = Path(
        description="Webhook id (wh_<uuid>).",
        examples=["wh_123e4567-e89b-12d3-a456-426614174000"],
    ),
) -> AdminWebhooksDeleteResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    webhook_id = validate_webhook_id_param(webhook_id)
    try:
        result = await backend.admin_webhook_delete(admin=admin, webhook_id=webhook_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="webhook not found")

    return AdminWebhooksDeleteResponse(
        webhook=result,
        metadata={},
    )
