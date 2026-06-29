# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from fastapi import APIRouter, HTTPException, Path, Request
from mail_protocol.core.lists import MAILListPolicy
from mail_protocol.network.requests import (
    AdminListPatchRequest,
    AdminListPostRequest,
    ListMemberPostRequest,
)
from mail_protocol.network.responses import (
    AdminListDeleteResponse,
    AdminListGetResponse,
    AdminListPatchResponse,
    AdminListPostResponse,
    AdminListsGetResponse,
    ListGetResponse,
    ListMemberDeleteResponse,
    ListMemberPostResponse,
    ListsGetResponse,
)

from mail_server.auth import validate_admin, validate_user_agent
from mail_server.backends.base import MAILServerBackend
from mail_server.validators import (
    validate_local_address_param,
    validate_member_address_param,
)

admin_router = APIRouter(prefix="/admin/lists", tags=["admin-lists"])
public_router = APIRouter(prefix="/lists", tags=["lists"])

_LOCAL_ADDRESS_PATH = Path(
    description="List local address (name@swarm); the list: prefix and host are implied.",
    examples=["announce@acme"],
)


def _full_list_address(backend: MAILServerBackend, local_address: str) -> str:
    """
    Reconstruct a list's full canonical ``list:name@swarm@host`` address
    from the local ``name@swarm`` path param. The path param carries only
    the local identifier; the ``list:`` prefix is implied by the route and
    the host by the server.
    """

    return f"list:{local_address}@{backend.host}"


#
# Policy guardrails — v1 ships only the open / public variants. The
# protocol layer accepts the closed variants so future contributions
# can extend the server without a protocol revision; until those land,
# any closed variant rejects at the endpoint layer with 501.
#
_V1_VISIBILITY = "public"
_V1_JOIN_POLICY = "open"
_V1_SEND_POLICY = "open"


def _reject_unsupported_policy(policy: MAILListPolicy | None) -> None:
    if policy is None:
        return
    if policy.visibility != _V1_VISIBILITY:
        raise HTTPException(
            status_code=501,
            detail=(
                f"list visibility {policy.visibility!r} is reserved at v1; "
                f"only {_V1_VISIBILITY!r} is honored."
            ),
        )
    if policy.join_policy != _V1_JOIN_POLICY:
        raise HTTPException(
            status_code=501,
            detail=(
                f"list join_policy {policy.join_policy!r} is reserved at v1; "
                f"only {_V1_JOIN_POLICY!r} is honored."
            ),
        )
    if policy.send_policy != _V1_SEND_POLICY:
        raise HTTPException(
            status_code=501,
            detail=(
                f"list send_policy {policy.send_policy!r} is reserved at v1; "
                f"only {_V1_SEND_POLICY!r} is honored."
            ),
        )


#
# Admin endpoints
#
@admin_router.get(
    "",
    summary="Get all MAIL lists known to this server",
    response_model=AdminListsGetResponse,
)
async def admin_get_lists(request: Request) -> AdminListsGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    result = await backend.admin_get_lists(admin=admin)
    return AdminListsGetResponse(lists=result, metadata={})


@admin_router.get(
    "/{local_address}",
    summary="Get a specific MAIL list by local address (name@swarm)",
    response_model=AdminListGetResponse,
)
async def admin_get_list(
    request: Request, local_address: str = _LOCAL_ADDRESS_PATH
) -> AdminListGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    list_address = _full_list_address(
        backend, validate_local_address_param(local_address)
    )
    try:
        result = await backend.admin_get_list(admin=admin, list_address=list_address)
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return AdminListGetResponse(mail_list=result, metadata={})


@admin_router.post(
    "",
    summary="Create a new MAIL list on this server",
    response_model=AdminListPostResponse,
)
async def admin_post_list(
    request: Request, payload: AdminListPostRequest
) -> AdminListPostResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    _reject_unsupported_policy(payload.policy)
    try:
        result = await backend.admin_post_list(admin=admin, payload=payload)
    except ValueError:
        raise HTTPException(status_code=409, detail="list address already taken")
    return AdminListPostResponse(mail_list=result, metadata={})


@admin_router.patch(
    "/{local_address}",
    summary="Update a MAIL list's policy",
    response_model=AdminListPatchResponse,
)
async def admin_patch_list(
    request: Request,
    payload: AdminListPatchRequest,
    local_address: str = _LOCAL_ADDRESS_PATH,
) -> AdminListPatchResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    list_address = _full_list_address(
        backend, validate_local_address_param(local_address)
    )
    _reject_unsupported_policy(payload.policy)
    try:
        result = await backend.admin_patch_list(
            admin=admin, list_address=list_address, payload=payload
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return AdminListPatchResponse(mail_list=result, metadata={})


@admin_router.delete(
    "/{local_address}",
    summary="Delete a MAIL list",
    response_model=AdminListDeleteResponse,
)
async def admin_delete_list(
    request: Request, local_address: str = _LOCAL_ADDRESS_PATH
) -> AdminListDeleteResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    list_address = _full_list_address(
        backend, validate_local_address_param(local_address)
    )
    try:
        result = await backend.admin_delete_list(admin=admin, list_address=list_address)
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return AdminListDeleteResponse(mail_list=result, metadata={})


@admin_router.post(
    "/{local_address}/members",
    summary="Admin-add a member to a MAIL list",
    response_model=ListMemberPostResponse,
)
async def admin_add_list_member(
    request: Request,
    payload: ListMemberPostRequest,
    local_address: str = _LOCAL_ADDRESS_PATH,
) -> ListMemberPostResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    _ = admin  # auth-only; the backend method does not gate by admin
    list_address = _full_list_address(
        backend, validate_local_address_param(local_address)
    )
    try:
        result = await backend.add_list_member(
            list_address=list_address,
            member_address=payload.member_address,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return ListMemberPostResponse(mail_list=result, metadata={})


@admin_router.delete(
    "/{local_address}/members/{member_address}",
    summary="Admin-remove a member from a MAIL list",
    response_model=ListMemberDeleteResponse,
)
async def admin_remove_list_member(
    request: Request,
    local_address: str = _LOCAL_ADDRESS_PATH,
    member_address: str = Path(
        description="Full MAIL address of the member to remove (may be remote).",
        examples=["user:bob@other-host"],
    ),
) -> ListMemberDeleteResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    _ = admin
    list_address = _full_list_address(
        backend, validate_local_address_param(local_address)
    )
    member_address = validate_member_address_param(member_address)
    try:
        result = await backend.remove_list_member(
            list_address=list_address,
            member_address=member_address,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return ListMemberDeleteResponse(mail_list=result, metadata={})


#
# Public endpoints
#
@public_router.get(
    "",
    summary="Get lists visible to the caller",
    response_model=ListsGetResponse,
)
async def get_lists(request: Request) -> ListsGetResponse:
    backend = request.app.state.backend
    # The caller must be authenticated, but visibility filtering at v1
    # is "all lists are public," so we return everything the backend
    # knows about. Future private-list support filters here.
    await validate_user_agent(backend=backend, request=request)
    result = await backend.get_lists()
    visible = [ml for ml in result if ml.policy.visibility == _V1_VISIBILITY]
    return ListsGetResponse(lists=visible, metadata={})


@public_router.get(
    "/{local_address}",
    summary="Get a specific list by local address (name@swarm)",
    response_model=ListGetResponse,
)
async def get_list(
    request: Request, local_address: str = _LOCAL_ADDRESS_PATH
) -> ListGetResponse:
    backend = request.app.state.backend
    await validate_user_agent(backend=backend, request=request)
    list_address = _full_list_address(
        backend, validate_local_address_param(local_address)
    )
    try:
        result = await backend.get_list(list_address=list_address)
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    if result.policy.visibility != _V1_VISIBILITY:
        # Private lists exist only via the admin surface at v1.
        raise HTTPException(status_code=404, detail="list not found")
    return ListGetResponse(mail_list=result, metadata={})


@public_router.post(
    "/{local_address}/subscribe",
    summary="Subscribe to a MAIL list",
    response_model=ListMemberPostResponse,
)
async def subscribe(
    request: Request, local_address: str = _LOCAL_ADDRESS_PATH
) -> ListMemberPostResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    list_address = _full_list_address(
        backend, validate_local_address_param(local_address)
    )

    try:
        existing = await backend.get_list(list_address=list_address)
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")

    if existing.policy.join_policy != _V1_JOIN_POLICY:
        raise HTTPException(
            status_code=501,
            detail=(
                f"list join_policy {existing.policy.join_policy!r} is "
                f"reserved at v1; only {_V1_JOIN_POLICY!r} is honored."
            ),
        )

    result = await backend.add_list_member(
        list_address=list_address,
        member_address=user_agent.get_address(),
    )
    return ListMemberPostResponse(mail_list=result, metadata={})


@public_router.post(
    "/{local_address}/unsubscribe",
    summary="Unsubscribe from a MAIL list",
    response_model=ListMemberDeleteResponse,
)
async def unsubscribe(
    request: Request, local_address: str = _LOCAL_ADDRESS_PATH
) -> ListMemberDeleteResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    list_address = _full_list_address(
        backend, validate_local_address_param(local_address)
    )
    member_address = user_agent.get_address()

    try:
        result = await backend.remove_list_member(
            list_address=list_address,
            member_address=member_address,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return ListMemberDeleteResponse(mail_list=result, metadata={})
