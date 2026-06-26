# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import HTTPException, Request
from mail_protocol.core.validators import (
    validate_daemon_worker_name,
    validate_local_address,
    validate_mail_address,
    validate_swarm_name,
    validate_user_name,
    validate_webhook_id,
)
from mail_protocol.network.requests import (
    AdminAgentPostRequest,
    AdminDaemonPostRequest,
    AdminListPatchRequest,
    AdminListPostRequest,
    AdminSwarmPostRequest,
    AdminUserPostRequest,
    AdminWebhooksPatchRequest,
    AdminWebhooksPostRequest,
    AuthPasswordResetRequest,
    AuthRefreshPostRequest,
    BoxFilterParams,
    DaemonDeliverLocalRequest,
    DaemonDeliverRemoteRequest,
    DraftPatchRequest,
    DraftPostRequest,
    DraftSendPostRequest,
    ListMemberPostRequest,
)

# NOTE: the except clauses below catch ValueError, which covers both
# pydantic.ValidationError and json.JSONDecodeError — an unparseable
# body must 422 the same way an invalid one does.


#
# Query parameter validators
#
async def validate_box_filter_params(request: Request) -> BoxFilterParams:
    """
    Ensure the query string is valid for the "GET box" endpoints
    (`GET /inbox`, `GET /outbox`, `GET /trash`, `GET /drafts`).

    `BoxFilterParams` declares `extra="forbid"`, so an unknown query
    parameter 422s the same way an out-of-bounds `limit` does. Values
    arrive as strings; pydantic coerces and bounds-checks them.
    """

    try:
        return BoxFilterParams.model_validate(dict(request.query_params))
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"query parameter validation failed: {e}"
        )


#
# Path parameter validators
#
# Admin (and list) endpoints address resources by their *local*
# identifier — the host is implied by the server and the user-agent
# prefix (``daemon:``/``user:``/``list:``) is implied by the route.
# These helpers validate the shape of a path segment and 422 on
# malformed input, mirroring the body/query validators above. A
# well-formed-but-unknown id still 404s downstream.
#
def validate_local_address_param(value: str) -> str:
    """
    Validate an agent or list local address path param (``name@swarm``).
    """

    try:
        return validate_local_address(value)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"invalid local address path parameter: {e}"
        )


def validate_worker_name_param(value: str) -> str:
    """
    Validate a daemon ``worker_name`` path param.
    """

    try:
        return validate_daemon_worker_name(value)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"invalid worker name path parameter: {e}"
        )


def validate_user_id_param(value: str) -> str:
    """
    Validate a ``user_id`` path param.
    """

    try:
        return validate_user_name(value)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"invalid user id path parameter: {e}"
        )


def validate_swarm_name_param(value: str) -> str:
    """
    Validate a ``swarm_name`` path param.
    """

    try:
        return validate_swarm_name(value)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"invalid swarm name path parameter: {e}"
        )


def validate_webhook_id_param(value: str) -> str:
    """
    Validate a ``webhook_id`` path param (``wh_<uuid>``).
    """

    try:
        return validate_webhook_id(value)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"invalid webhook id path parameter: {e}"
        )


def validate_member_address_param(value: str) -> str:
    """
    Validate a list ``member_address`` path param. Unlike the resource
    identifiers above, a member can be any user-agent — possibly on
    another host — so this is a full MAIL address, not a local one.
    """

    try:
        return validate_mail_address(value)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"invalid member address path parameter: {e}"
        )


#
# Draft endpoint validators
#
async def validate_post_draft_request(request: Request) -> DraftPostRequest:
    """
    Ensure the request payload is valid for `POST /drafts`.
    """

    try:
        body = await request.json()
        return DraftPostRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_patch_draft_request(request: Request) -> DraftPatchRequest:
    """
    Ensure the request payload is valid for `PATCH /drafts/{draft_id}`.
    """

    try:
        body = await request.json()
        return DraftPatchRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_post_draft_send_request(request: Request) -> DraftSendPostRequest:
    """
    Ensure the request payload is valid for `POST /drafts/{draft_id}/send`.
    """

    try:
        body = await request.json()
        return DraftSendPostRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


#
# Daemon endpoint validators
#
async def validate_deliver_local_request(
    request: Request,
) -> DaemonDeliverLocalRequest:
    """
    Ensure that the request payload is valid for `POST /daemon/deliver/local`.
    """

    try:
        body = await request.json()
        return DaemonDeliverLocalRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_deliver_remote_request(
    request: Request,
) -> DaemonDeliverRemoteRequest:
    """
    Ensure that the request payload is valid for `POST /daemon/deliver/remote`.
    """

    try:
        body = await request.json()
        return DaemonDeliverRemoteRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


#
# Admin endpoint validators
#
async def validate_admin_post_agent_request(
    request: Request,
) -> AdminAgentPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/agents`.
    """

    try:
        body = await request.json()
        return AdminAgentPostRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_post_daemon_request(
    request: Request,
) -> AdminDaemonPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/daemons`.
    """

    try:
        body = await request.json()
        return AdminDaemonPostRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_post_user_request(
    request: Request,
) -> AdminUserPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/users`.
    """

    try:
        body = await request.json()
        return AdminUserPostRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_post_swarm_request(
    request: Request,
) -> AdminSwarmPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/swarms`.
    """

    try:
        body = await request.json()
        return AdminSwarmPostRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_webhook_post_request(
    request: Request,
) -> AdminWebhooksPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/webhooks`.
    """

    try:
        body = await request.json()
        return AdminWebhooksPostRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_webhook_patch_request(
    request: Request,
) -> AdminWebhooksPatchRequest:
    """
    Ensure that the given request payload is valid for `PATCH /admin/webhooks`.
    """

    try:
        body = await request.json()
        return AdminWebhooksPatchRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_post_list_request(
    request: Request,
) -> AdminListPostRequest:
    """
    Ensure that the request payload is valid for `POST /admin/lists`.
    """

    try:
        body = await request.json()
        return AdminListPostRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_admin_patch_list_request(
    request: Request,
) -> AdminListPatchRequest:
    """
    Ensure that the request payload is valid for `PATCH /admin/lists/{local_address}`.
    """

    try:
        body = await request.json()
        return AdminListPatchRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_list_member_post_request(
    request: Request,
) -> ListMemberPostRequest:
    """
    Ensure that the request payload is valid for the member-add endpoints
    (`POST /admin/lists/{local_address}/members` and the subscribe variant).
    """

    try:
        body = await request.json()
        return ListMemberPostRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


#
# Auth endpoint validators
#
async def validate_auth_password_reset_request(
    request: Request,
) -> AuthPasswordResetRequest:
    """
    Ensure that the request payload is valid for `POST /auth/password/reset`.
    """

    try:
        body = await request.json()
        return AuthPasswordResetRequest.model_validate(body)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )


async def validate_auth_refresh_request(
    request: Request,
) -> AuthRefreshPostRequest:
    """
    Ensure that the request payload is valid for `POST /auth/refresh`.

    An empty body is allowed: browsers carry the refresh token in the
    ``httpOnly`` cookie and may send no body at all. A non-empty body must still
    be valid JSON for the model, otherwise 422.
    """

    raw = await request.body()
    if not raw:
        return AuthRefreshPostRequest()
    try:
        return AuthRefreshPostRequest.model_validate_json(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=f"request body validation failed: {e}"
        )
