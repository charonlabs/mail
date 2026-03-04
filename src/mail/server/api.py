# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
import uuid
from datetime import datetime
from typing import Annotated

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    Response,
)

from mail.protocol.constants import MAIL_DEFAULT_PORT
from mail.protocol.core.address import MAILAddress
from mail.protocol.core.message import MAILMessage
from mail.server.auth import (
    TokenInfo,
    get_current_admin_or_user,
    get_current_swarm,
)
from mail.server.types import (
    EndpointFunction,
    PostInterswarmMessageHandler,
    PostInterswarmMessageRequest,
    PostInterswarmMessageResponse,
    PostMessageHandler,
    PostMessageRequest,
    PostMessageResponse,
)
from mail.server.validators import (
    ensure_swarm_names_match,
    validate_post_interswarm_message_request,
    validate_post_message_request,
)


class MAILServer:
    """
    A MAIL HTTP server.
    """
    def __init__(
        self,
        name: str,
        host: str = "127.0.0.1",
        port: int = MAIL_DEFAULT_PORT,
        reload: bool = False,
        description: str = "A MAIL HTTP server.",
        keywords: list[str] = [],
    ) -> None:
        self.name = name
        self.host = host
        self.port = port
        self.reload = reload
        self.description = description
        self.keywords = keywords

        app = FastAPI(
            title=name,
            description=description,
            keywords=keywords,
        )
        app.post
        self.app = app

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

            message_received, metadata = await func(message_to_send)

            response_body = PostInterswarmMessageResponse(
                message=message_received,
                metadata=metadata,
            ).model_dump()

            return Response(
                content=json.dumps(response_body),
                media_type="application/json",
            )
        
        return wrapper