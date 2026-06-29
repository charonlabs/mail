# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import HTTPException
from mail_protocol.core.validators import (
    validate_daemon_worker_name,
    validate_local_address,
    validate_mail_address,
    validate_swarm_name,
    validate_user_name,
    validate_webhook_id,
)

# Request bodies and query strings are validated by FastAPI from the typed
# parameters declared on each handler (the models live in
# ``mail_protocol.network.requests``). The helpers below cover only path
# parameters, which the handlers still validate explicitly.


#
# Path parameter validators
#
# Admin (and list) endpoints address resources by their *local*
# identifier — the host is implied by the server and the user-agent
# prefix (``daemon:``/``user:``/``list:``) is implied by the route.
# These helpers validate the shape of a path segment and 422 on
# malformed input, mirroring the body/query validation FastAPI performs.
# A well-formed-but-unknown id still 404s downstream.
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
