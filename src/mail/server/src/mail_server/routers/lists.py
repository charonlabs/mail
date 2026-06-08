# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from fastapi import APIRouter, HTTPException, Request
from mail_protocol.core.lists import MAILListPolicy
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
from mail_server.validators import (
    validate_admin_patch_list_request,
    validate_admin_post_list_request,
    validate_list_member_post_request,
)

admin_router = APIRouter(prefix="/admin/lists", tags=["admin-lists"])
public_router = APIRouter(prefix="/lists", tags=["lists"])


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
    "/{list_address}",
    summary="Get a specific MAIL list by address",
    response_model=AdminListGetResponse,
)
async def admin_get_list(request: Request) -> AdminListGetResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    list_address = request.path_params.get("list_address")
    try:
        result = await backend.admin_get_list(
            admin=admin, list_address=list_address
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return AdminListGetResponse(mail_list=result, metadata={})


@admin_router.post(
    "",
    summary="Create a new MAIL list on this server",
    response_model=AdminListPostResponse,
)
async def admin_post_list(request: Request) -> AdminListPostResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    payload = await validate_admin_post_list_request(request=request)
    _reject_unsupported_policy(payload.policy)
    try:
        result = await backend.admin_post_list(admin=admin, payload=payload)
    except ValueError:
        raise HTTPException(status_code=409, detail="list address already taken")
    return AdminListPostResponse(mail_list=result, metadata={})


@admin_router.patch(
    "/{list_address}",
    summary="Update a MAIL list's policy",
    response_model=AdminListPatchResponse,
)
async def admin_patch_list(request: Request) -> AdminListPatchResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    list_address = request.path_params.get("list_address")
    payload = await validate_admin_patch_list_request(request=request)
    _reject_unsupported_policy(payload.policy)
    try:
        result = await backend.admin_patch_list(
            admin=admin, list_address=list_address, payload=payload
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return AdminListPatchResponse(mail_list=result, metadata={})


@admin_router.delete(
    "/{list_address}",
    summary="Delete a MAIL list",
    response_model=AdminListDeleteResponse,
)
async def admin_delete_list(request: Request) -> AdminListDeleteResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    list_address = request.path_params.get("list_address")
    try:
        result = await backend.admin_delete_list(
            admin=admin, list_address=list_address
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return AdminListDeleteResponse(mail_list=result, metadata={})


@admin_router.post(
    "/{list_address}/members",
    summary="Admin-add a member to a MAIL list",
    response_model=ListMemberPostResponse,
)
async def admin_add_list_member(request: Request) -> ListMemberPostResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    _ = admin  # auth-only; the backend method does not gate by admin
    list_address = request.path_params.get("list_address")
    payload = await validate_list_member_post_request(request=request)
    try:
        result = await backend.add_list_member(
            list_address=list_address,
            member_address=payload.member_address,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return ListMemberPostResponse(mail_list=result, metadata={})


@admin_router.delete(
    "/{list_address}/members/{member_address}",
    summary="Admin-remove a member from a MAIL list",
    response_model=ListMemberDeleteResponse,
)
async def admin_remove_list_member(request: Request) -> ListMemberDeleteResponse:
    backend = request.app.state.backend
    admin = await validate_admin(backend=backend, request=request)
    _ = admin
    list_address = request.path_params.get("list_address")
    member_address = request.path_params.get("member_address")
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
    "/{list_address}",
    summary="Get a specific list",
    response_model=ListGetResponse,
)
async def get_list(request: Request) -> ListGetResponse:
    backend = request.app.state.backend
    await validate_user_agent(backend=backend, request=request)
    list_address = request.path_params.get("list_address")
    try:
        result = await backend.get_list(list_address=list_address)
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    if result.policy.visibility != _V1_VISIBILITY:
        # Private lists exist only via the admin surface at v1.
        raise HTTPException(status_code=404, detail="list not found")
    return ListGetResponse(mail_list=result, metadata={})


@public_router.post(
    "/{list_address}/members",
    summary="Subscribe to a MAIL list",
    response_model=ListMemberPostResponse,
)
async def subscribe(request: Request) -> ListMemberPostResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    list_address = request.path_params.get("list_address")
    payload = await validate_list_member_post_request(request=request)

    # v1 join_policy = "open" — anyone authenticated may subscribe, but
    # the requested member address must match the bearer's own
    # address. Self-subscribe only at this endpoint.
    if payload.member_address != user_agent.get_address():
        raise HTTPException(
            status_code=403,
            detail=(
                "subscribe is self-only; use the admin endpoint to add "
                "another member."
            ),
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
        member_address=payload.member_address,
    )
    return ListMemberPostResponse(mail_list=result, metadata={})


@public_router.delete(
    "/{list_address}/members/{member_address}",
    summary="Leave a MAIL list",
    response_model=ListMemberDeleteResponse,
)
async def unsubscribe(request: Request) -> ListMemberDeleteResponse:
    backend = request.app.state.backend
    user_agent = await validate_user_agent(backend=backend, request=request)
    list_address = request.path_params.get("list_address")
    member_address = request.path_params.get("member_address")

    if member_address != user_agent.get_address():
        raise HTTPException(
            status_code=403,
            detail=(
                "unsubscribe is self-only; use the admin endpoint to "
                "remove another member."
            ),
        )

    try:
        result = await backend.remove_list_member(
            list_address=list_address,
            member_address=member_address,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="list not found")
    return ListMemberDeleteResponse(mail_list=result, metadata={})
