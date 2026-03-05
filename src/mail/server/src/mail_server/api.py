# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
import time
import uuid
from datetime import datetime
from typing import Annotated

import aiohttp
import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Response,
)
from mail_protocol.constants import MAIL_DEFAULT_PORT
from mail_protocol.core.address import MAILAddress
from mail_protocol.core.message import MAILMessage
from mail_protocol.core.swarm import MAILSwarm
from mail_protocol.interswarm import MAILRemoteSwarm
from mail_protocol.network.requests import (
    PostInterswarmMessageRequest,
    PostMessageRequest,
    PostRegistryRequest,
)
from mail_protocol.network.responses import (
    GetRegistryResponse,
    GetRootResponse,
    GetSwarmResponse,
    PostInterswarmMessageResponse,
    PostMessageResponse,
    PostRegistryResponse,
)

from mail_server.auth import (
    TokenInfo,
    get_current_admin_or_user,
    get_current_swarm,
)
from mail_server.types import (
    EndpointFunction,
    PostInterswarmMessageHandler,
    PostMessageHandler,
    SwarmRegistry,
)
from mail_server.validators import (
    ensure_swarm_names_match,
    validate_get_swarm_response,
    validate_post_interswarm_message_request,
    validate_post_message_request,
)


class MAILServer:
    """
    A MAIL HTTP server.
    """
    def __init__(
        self,
        swarm: MAILSwarm,
        host: str = "127.0.0.1",
        port: int = MAIL_DEFAULT_PORT,
        reload: bool = False,
    ) -> None:
        self.swarm = swarm
        self.host = host
        self.port = port
        self.reload = reload

        self.registry: SwarmRegistry = {}

        app = FastAPI(
            title=swarm.name,
            description=swarm.description,
            keywords=swarm.keywords,
        )
        self.app = app
        self._register_endpoints()

    def _register_endpoints(
        self,
    ) -> None:
        """
        Register server endpoints that need not be implemented by the user.
        """
        self.app.get("/")(self._on_get_root)
        self.app.get("/swarm")(self._on_get_swarm)
        self.app.get("/registry")(self._on_get_registry)
        self.app.post("/registry")(self._on_post_registry)
        raise NotImplementedError

    def run(
        self,
    ) -> None:
        """
        Run this server.
        """
        uvicorn.run(self.app, host=self.host, port=self.port, reload=self.reload)

    def on_message(
        self,
        func: PostMessageHandler
    ) -> EndpointFunction:
        """
        Handle the MAIL server's `POST /message` endpoint.
        e.g. `@server.on_message(handle_message)` decorator.
        """
        @self.app.post("/message")
        async def wrapper(
            request: Annotated[PostMessageRequest, Depends(validate_post_message_request)],
            client: Annotated[TokenInfo, Depends(get_current_admin_or_user)]
        ) -> Response:
            client_id = client.id
            client_role = client.role

            message_to_send = MAILMessage(
                id=str(uuid.uuid4()),
                timestamp=str(datetime.now()),
                msg_type=request.msg_type,
                sender=MAILAddress(addr_type=client_role, address=client_id),
                recipients=request.recipients,
                subject=request.subject,
                body=request.body,
                task_id=request.task_id,
                metadata=request.metadata,
            )
            message_received, metadata = await func(message_to_send)

            response_body = PostMessageResponse(
                message=message_received,
                metadata=metadata,
            ).model_dump()

            return Response(
                content=json.dumps(response_body),
                media_type="application/json",
            )

        return wrapper

    def on_interswarm(
        self,
        func: PostInterswarmMessageHandler
    ) -> EndpointFunction:
        """
        Handle the MAIL server's `POST /interswarm/message` endpoint.
        e.g. `@server.on_interswarm(handle_interswarm_message)` decorator.
        """
        @self.app.post("/interswarm/message")
        async def wrapper(
            request: Annotated[PostInterswarmMessageRequest, Depends(validate_post_interswarm_message_request)],
            client: Annotated[TokenInfo, Depends(get_current_swarm)]
        ) -> Response:
            client_id = client.id
            message_to_send = request.message
            ensure_swarm_names_match(client_id, message_to_send.source_swarm)

            status, new_task, metadata = await func(message_to_send)

            response_body = PostInterswarmMessageResponse(
                status=status,
                new_task=new_task,
                metadata=metadata,
            ).model_dump()

            return Response(
                content=json.dumps(response_body),
                media_type="application/json",
            )
        
        return wrapper

    async def _on_get_root(
        self,
    ) -> GetRootResponse:
        """
        Handle the MAIL server's `GET /` endpoint.
        """
        uptime = time.time() - self.app.state.time_startup

        return GetRootResponse(
            protocol_name="mail",
            protocol_version="2.0",
            status="running",
            uptime=uptime,
            metadata={},
        )

    async def _on_get_swarm(
        self,
    ) -> GetSwarmResponse:
        """
        Handle the MAIL server's `GET /swarm` endpoint.
        """
        return GetSwarmResponse(
            swarm=self.swarm,
            status="running",
            metadata={},
        )

    async def _on_get_registry(
        self,
    ) -> GetRegistryResponse:
        """
        Handle the MAIL server's `GET /registry` endpoint.
        """
        return GetRegistryResponse(
            swarms=self.registry,
            metadata={},
        )

    async def _on_post_registry(
        self,
        request: PostRegistryRequest,
    ) -> PostRegistryResponse:
        """
        Handle the MAIL server's `POST /registry` endpoint.
        """
        base_url = request.base_url.rstrip("/")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/swarm") as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=504,
                        detail="failed to get swarm info from remote swarm",
                    )
                response_obj = await validate_get_swarm_response(response)
                remote_swarm = MAILRemoteSwarm(
                    name=response_obj.swarm.name,
                    base_url=base_url,
                    protocol_version=response_obj.protocol_version,
                    active=True if response_obj.status == "running" else False,
                    last_seen=str(datetime.now()),
                    description=response_obj.swarm.description,
                    keywords=response_obj.swarm.keywords,
                    metadata=response_obj.swarm.metadata,
                )
                return PostRegistryResponse(
                    status="success",
                    swarm=remote_swarm,
                    metadata={},
                )