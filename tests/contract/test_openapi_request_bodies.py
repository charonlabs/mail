# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
Guards that every body-bearing POST/PATCH endpoint documents its request
body in the OpenAPI schema, and that the "GET box" endpoints document their
query parameters.

Handlers that take only ``request: Request`` and parse the body/query string
by hand produce no schema for it, so the bodies silently vanish from
``/docs``. This test fails if that regression is reintroduced.
"""

import pytest

# (path, method) for every endpoint that MUST advertise a JSON request body.
ENDPOINTS_WITH_BODY = [
    ("/auth/refresh", "post"),
    ("/auth/logout", "post"),
    ("/auth/password/reset", "post"),
    ("/drafts", "post"),
    ("/drafts/{draft_id}", "patch"),
    ("/drafts/{draft_id}/send", "post"),
    ("/daemon/deliver/local", "post"),
    ("/daemon/deliver/remote", "post"),
    ("/admin/agents", "post"),
    ("/admin/daemons", "post"),
    ("/admin/users", "post"),
    ("/admin/swarms", "post"),
    ("/admin/webhooks", "post"),
    ("/admin/webhooks/{webhook_id}", "patch"),
    ("/admin/lists", "post"),
    ("/admin/lists/{local_address}", "patch"),
    ("/admin/lists/{local_address}/members", "post"),
]

# Endpoints that intentionally take no body — the member is derived from the
# authenticated caller, or the action has no parameters. These must NOT grow
# a request body.
ENDPOINTS_WITHOUT_BODY = [
    ("/trash/clear", "post"),
    ("/daemon/message-buffer/clear", "post"),
    ("/lists/{local_address}/subscribe", "post"),
    ("/lists/{local_address}/unsubscribe", "post"),
]

# "GET box" endpoints whose BoxFilterParams query params must be documented.
BOX_GET_PATHS = ["/inbox", "/outbox", "/trash", "/drafts"]
BOX_QUERY_PARAMS = {"limit", "offset", "sort_by", "order"}


@pytest.fixture(scope="module")
def schema() -> dict:
    from mail_server.server import app

    return app.openapi()


@pytest.mark.parametrize("path,method", ENDPOINTS_WITH_BODY)
def test_endpoint_documents_request_body(schema: dict, path: str, method: str) -> None:
    operation = schema["paths"][path][method]
    assert "requestBody" in operation, (
        f"{method.upper()} {path} has no documented request body — the handler "
        "likely takes only `request: Request` and parses the body by hand. "
        "Declare the request model as a typed parameter."
    )
    content = operation["requestBody"].get("content", {})
    assert "application/json" in content, (
        f"{method.upper()} {path} request body is not application/json: "
        f"{list(content)}"
    )
    assert content["application/json"].get("schema"), (
        f"{method.upper()} {path} request body has no schema"
    )


@pytest.mark.parametrize("path,method", ENDPOINTS_WITHOUT_BODY)
def test_bodyless_endpoint_has_no_request_body(
    schema: dict, path: str, method: str
) -> None:
    operation = schema["paths"][path][method]
    assert "requestBody" not in operation, (
        f"{method.upper()} {path} unexpectedly advertises a request body; "
        "this endpoint is supposed to take no body."
    )


@pytest.mark.parametrize("path", BOX_GET_PATHS)
def test_box_get_documents_query_params(schema: dict, path: str) -> None:
    params = {
        p["name"]
        for p in schema["paths"][path]["get"].get("parameters", [])
        if p["in"] == "query"
    }
    missing = BOX_QUERY_PARAMS - params
    assert not missing, (
        f"GET {path} is missing query params {missing} in the schema — the "
        "handler likely parses the query string by hand instead of declaring "
        "BoxFilterParams as a typed Query() parameter."
    )
