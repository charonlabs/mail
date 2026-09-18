# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Public discovery and signed Federation v1 ingress endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from mail_protocol.core.federation import MAILFederationManifest, MAILInterServerMessage
from mail_protocol.network.federation import (
    FEDERATION_DELIVERY_PATH_V1,
    FEDERATION_DISCOVERY_PATH,
    MAILFederationAcceptedResponse,
    MAILFederationErrorResponse,
)
from pydantic import BaseModel

from mail_server.federation.ingress import FederationIngressService

router = APIRouter(tags=["federation"])
logger = logging.getLogger(__name__)


def _inline_openapi_schema() -> dict[str, object]:
    """Inline Pydantic's local ``$defs`` into a valid OpenAPI request schema."""

    schema = MAILInterServerMessage.model_json_schema()
    definitions = schema.pop("$defs", {})

    def inline(value: object) -> object:
        if isinstance(value, list):
            return [inline(item) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/")
            return inline(definitions[name])
        return {key: inline(item) for key, item in value.items()}

    result = inline(schema)
    assert isinstance(result, dict)
    return result


_ENVELOPE_OPENAPI_SCHEMA = _inline_openapi_schema()


def _json_response(status_code: int, model: BaseModel) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=model.model_dump(mode="json", exclude_none=True),
    )


@router.get(FEDERATION_DISCOVERY_PATH, response_model=MAILFederationManifest)
async def get_federation_manifest(request: Request) -> Response:
    runtime = request.app.state.federation
    if not runtime.enabled:
        return Response(status_code=404)
    config = runtime.config
    assert config is not None
    return JSONResponse(
        content=config.manifest.model_dump(mode="json", exclude_none=True),
        headers={"Cache-Control": f"public, max-age={config.discovery_ttl_seconds}"},
    )


async def _limited_body(request: Request, limit: int) -> bytes | None:
    content_length = request.headers.get("Content-Length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = -1
        if declared < 0:
            return b""
        if declared > limit:
            return None

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    FEDERATION_DELIVERY_PATH_V1,
    status_code=202,
    response_model=MAILFederationAcceptedResponse,
    responses={
        400: {"model": MAILFederationErrorResponse},
        401: {"model": MAILFederationErrorResponse},
        403: {"model": MAILFederationErrorResponse},
        404: {"model": MAILFederationErrorResponse},
        409: {"model": MAILFederationErrorResponse},
        413: {"model": MAILFederationErrorResponse},
        503: {"model": MAILFederationErrorResponse},
    },
    summary="Accept one signed Federation v1 envelope",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": _ENVELOPE_OPENAPI_SCHEMA}},
        }
    },
)
async def deliver_federation_message(request: Request) -> Response:
    # FastAPI advertises the body schema, while ingress consumes the original
    # ASGI bytes so Content-Digest and the cap apply before model validation.
    runtime = request.app.state.federation
    if not runtime.enabled:
        return Response(status_code=404)
    config = runtime.config
    discovery = runtime.discovery
    assert config is not None and discovery is not None

    if request.scope.get("query_string"):
        return _json_response(
            400,
            MAILFederationErrorResponse(
                code="invalid_envelope",
                detail="federation delivery URL must not contain a query",
            ),
        )

    body = await _limited_body(request, config.max_request_bytes)
    if body is None:
        return _json_response(
            413,
            MAILFederationErrorResponse(
                code="payload_too_large",
                detail="federation request exceeds the configured size limit",
            ),
        )

    service = FederationIngressService(config=config, discovery=discovery)
    try:
        result = await service.accept(
            backend=request.app.state.backend,
            method=request.method,
            target_url=config.delivery_url,
            headers=request.headers.raw,
            body=body,
            transport_is_secure=request.url.scheme == "https",
        )
    except Exception:
        logger.exception("federation ingress failed before durable acceptance")
        return _json_response(
            503,
            MAILFederationErrorResponse(
                code="temporarily_unavailable",
                detail="federation ingress is temporarily unavailable",
            ),
        )
    return _json_response(result.status_code, result.body)
