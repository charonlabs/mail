# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

import inspect
import json
import os
import time
import uuid
from collections.abc import Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import aiohttp
import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from mail_protocol.constants import MAIL_DEFAULT_PORT
from mail_protocol.core.address import MAILAddress
from mail_protocol.core.message import MAILMessage
from mail_protocol.core.swarm import MAILSwarm
from mail_protocol.interswarm import MAILRemoteSwarm
from mail_protocol.network.requests import (
    LoginRequest,
    PostInterswarmMessageRequest,
    PostMessageRequest,
    PostRegistryRequest,
)
from mail_protocol.network.responses import (
    DeleteRegistryResponse,
    GetRegistryResponse,
    GetRootResponse,
    GetSwarmResponse,
    LoginResponse,
    PostInterswarmMessageResponse,
    PostMessageResponse,
    PostRegistryResponse,
    WhoamiResponse,
)

from mail_server.auth import (
    APIKeyAuthBackend,
    JWTSettings,
    MAILServerAuth,
    TokenInfo,
    get_auth_settings,
    get_current_admin,
    get_current_admin_or_user,
    get_current_swarm,
)
from mail_server.types import (
    LifecycleHandler,
    PersistedSwarmRegistry,
    PostInterswarmMessageHandler,
    PostMessageHandler,
    SwarmRegistry,
    SwarmRegistryEntry,
)
from mail_server.utils import get_user_agent
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
        registry_path: str | os.PathLike[str] | None = None,
        auth_backend: APIKeyAuthBackend | None = None,
        auth_settings: JWTSettings | None = None,
    ) -> None:
        self.swarm = swarm
        self.host = host
        self.port = port
        self.reload = reload
        self.registry_path = Path(registry_path) if registry_path is not None else None
        self.auth = self._build_auth(
            auth_backend=auth_backend,
            auth_settings=auth_settings,
        )

        self.registry: SwarmRegistry = {}
        self._http_session: aiohttp.ClientSession | None = None
        self._message_handler: PostMessageHandler | None = None
        self._interswarm_handler: PostInterswarmMessageHandler | None = None
        self._startup_handlers: list[LifecycleHandler] = []
        self._shutdown_handlers: list[LifecycleHandler] = []

        self.app = FastAPI(
            title=swarm.name,
            lifespan=self._lifespan,
        )
        self._register_endpoints()

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        await self._initialize_state(app)
        try:
            await self._run_lifecycle_handlers(self._startup_handlers)
            yield
        finally:
            await self._run_lifecycle_handlers(reversed(self._shutdown_handlers))
            await self._teardown_state(app)

    async def _initialize_state(self, app: FastAPI) -> None:
        app.state.mail_server = self
        app.state.mail_server_auth = self.auth
        app.state.time_startup = time.time()
        self._http_session = aiohttp.ClientSession(
            headers={"User-Agent": get_user_agent()}
        )
        app.state.http_session = self._http_session

        if self.registry_path is not None:
            self._load_registry()

    async def _teardown_state(self, app: FastAPI) -> None:
        if self.registry_path is not None:
            self._save_registry()

        if self._http_session is not None and not self._http_session.closed:
            await self._http_session.close()

        self._http_session = None
        app.state.http_session = None
        app.state.mail_server_auth = None

    def _register_endpoints(self) -> None:
        """
        Register built-in MAIL server endpoints.
        """
        self.app.get("/")(self._on_get_root)
        self.app.get("/swarm")(self._on_get_swarm)
        self.app.get("/registry")(self._on_get_registry)
        self.app.post("/login")(self._on_post_login)
        self.app.get("/whoami")(self._on_get_whoami)
        self.app.post("/registry")(self._on_post_registry)
        self.app.delete("/registry/{swarm_name}")(self._on_delete_registry)
        self.app.post("/message")(self._handle_post_message)
        self.app.post("/interswarm/message")(self._handle_post_interswarm_message)

    @staticmethod
    def _build_auth(
        *,
        auth_backend: APIKeyAuthBackend | None,
        auth_settings: JWTSettings | None,
    ) -> MAILServerAuth | None:
        if auth_backend is None and auth_settings is None:
            return None

        resolved_auth_settings = auth_settings or get_auth_settings()
        return MAILServerAuth(
            settings=resolved_auth_settings,
            api_key_backend=auth_backend,
        )

    def run(self) -> None:
        """
        Run this server.
        """
        uvicorn.run(self.app, host=self.host, port=self.port, reload=self.reload)

    def on_message(self, func: PostMessageHandler) -> PostMessageHandler:
        """
        Register the MAIL server's `POST /message` handler.
        """
        if self._message_handler is not None:
            raise RuntimeError("`POST /message` handler already registered")
        self._message_handler = func
        return func

    def on_interswarm(
        self,
        func: PostInterswarmMessageHandler,
    ) -> PostInterswarmMessageHandler:
        """
        Register the MAIL server's `POST /interswarm/message` handler.
        """
        if self._interswarm_handler is not None:
            raise RuntimeError("`POST /interswarm/message` handler already registered")
        self._interswarm_handler = func
        return func

    def on_startup(self, func: LifecycleHandler) -> LifecycleHandler:
        """
        Register a startup hook.
        """
        self._validate_lifecycle_handler(func)
        self._startup_handlers.append(func)
        return func

    def on_shutdown(self, func: LifecycleHandler) -> LifecycleHandler:
        """
        Register a shutdown hook.
        """
        self._validate_lifecycle_handler(func)
        self._shutdown_handlers.append(func)
        return func

    @staticmethod
    def _validate_lifecycle_handler(func: LifecycleHandler) -> None:
        signature = inspect.signature(func)
        positional_params = [
            param
            for param in signature.parameters.values()
            if param.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        required_keyword_only = [
            param
            for param in signature.parameters.values()
            if param.kind == inspect.Parameter.KEYWORD_ONLY
            and param.default is inspect.Signature.empty
        ]

        if len(positional_params) > 1 or required_keyword_only:
            raise TypeError(
                "lifecycle handlers must accept either zero args or a single "
                "`MAILServer` positional argument"
            )

    async def _run_lifecycle_handlers(
        self,
        handlers: Iterable[LifecycleHandler],
    ) -> None:
        for handler in handlers:
            await self._call_lifecycle_handler(handler)

    async def _call_lifecycle_handler(self, handler: LifecycleHandler) -> None:
        signature = inspect.signature(handler)
        positional_params = [
            param
            for param in signature.parameters.values()
            if param.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]

        if positional_params:
            result = handler(self)
        else:
            result = handler()

        if inspect.isawaitable(result):
            await result

    async def _handle_post_message(
        self,
        request: Annotated[
            PostMessageRequest,
            Depends(validate_post_message_request),
        ],
        client: Annotated[TokenInfo, Depends(get_current_admin_or_user)],
    ) -> JSONResponse:
        """
        Handle the MAIL server's `POST /message` endpoint.
        """
        if self._message_handler is None:
            raise HTTPException(
                status_code=501,
                detail="`POST /message` handler is not configured",
            )

        message_to_send = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC).isoformat(),
            msg_type=request.msg_type,
            sender=MAILAddress(addr_type=client.role, address=client.id),
            recipients=request.recipients,
            subject=request.subject,
            body=request.body,
            task_id=request.task_id,
            metadata=request.metadata,
        )
        message_received, metadata = await self._message_handler(message_to_send)

        response_body = PostMessageResponse(
            message=message_received,
            metadata=metadata,
        ).model_dump(mode="json")
        return JSONResponse(content=response_body)

    async def _handle_post_interswarm_message(
        self,
        request: Annotated[
            PostInterswarmMessageRequest,
            Depends(validate_post_interswarm_message_request),
        ],
        client: Annotated[TokenInfo, Depends(get_current_swarm)],
    ) -> JSONResponse:
        """
        Handle the MAIL server's `POST /interswarm/message` endpoint.
        """
        if self._interswarm_handler is None:
            raise HTTPException(
                status_code=501,
                detail="`POST /interswarm/message` handler is not configured",
            )

        message_to_send = request.message
        ensure_swarm_names_match(client.id, message_to_send.source_swarm)

        response_obj = await self._interswarm_handler(message_to_send)
        response_body = PostInterswarmMessageResponse(
            status=response_obj.status,
            new_task=response_obj.new_task,
            metadata=response_obj.metadata,
        ).model_dump(mode="json")
        return JSONResponse(content=response_body)

    async def _on_get_root(self) -> GetRootResponse:
        """
        Handle the MAIL server's `GET /` endpoint.
        """
        startup_time = getattr(self.app.state, "time_startup", time.time())
        uptime = max(0.0, time.time() - startup_time)

        return GetRootResponse(
            protocol_name="mail",
            protocol_version="2.0",
            status="running",
            uptime=uptime,
            metadata={},
        )

    async def _on_get_swarm(self) -> GetSwarmResponse:
        """
        Handle the MAIL server's `GET /swarm` endpoint.
        """
        return GetSwarmResponse(
            swarm=self.swarm,
            protocol_version="2.0",
            status="running",
            metadata={},
        )

    async def _on_get_registry(self) -> GetRegistryResponse:
        """
        Handle the MAIL server's `GET /registry` endpoint.
        """
        public_registry: dict[str, MAILRemoteSwarm] = {
            swarm_name: entry.swarm
            for swarm_name, entry in self.registry.items()
            if entry.public
        }
        return GetRegistryResponse(
            swarms=public_registry,
            metadata={},
        )

    async def _on_post_login(
        self,
        request: LoginRequest,
    ) -> LoginResponse:
        """
        Handle the MAIL server's `POST /login` endpoint.
        """
        if self.auth is None:
            raise HTTPException(
                status_code=501,
                detail="MAIL server auth is not configured",
            )

        client = await self.auth.authenticate_api_key(request.api_key)
        access_token = self.auth.create_access_token(client)

        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            role=client.role,
            id=client.id,
            metadata={},
        )

    async def _on_get_whoami(
        self,
        client: Annotated[TokenInfo, Depends(get_current_admin_or_user)],
    ) -> WhoamiResponse:
        """
        Handle the MAIL server's `GET /whoami` endpoint.
        """
        return WhoamiResponse(
            id=client.id,
            role=client.role,
            metadata={},
        )

    async def _on_post_registry(
        self,
        request: PostRegistryRequest,
        _admin: Annotated[TokenInfo, Depends(get_current_admin)],
    ) -> PostRegistryResponse:
        """
        Handle the MAIL server's `POST /registry` endpoint.
        """
        api_key = os.getenv(request.api_key_ref)
        if api_key is None:
            raise HTTPException(
                status_code=400,
                detail="invalid API key reference",
            )

        remote_swarm = await self._fetch_remote_swarm(request.base_url.rstrip("/"))
        entry = SwarmRegistryEntry(
            swarm=remote_swarm,
            api_key_ref=request.api_key_ref,
            public=request.public,
            volatile=request.volatile,
        )
        self.registry[remote_swarm.name] = entry

        if self.registry_path is not None:
            self._save_registry()

        return PostRegistryResponse(
            status="success",
            swarm=remote_swarm,
            metadata={},
        )

    async def _on_delete_registry(
        self,
        swarm_name: str,
        _admin: Annotated[TokenInfo, Depends(get_current_admin)],
    ) -> DeleteRegistryResponse:
        """
        Handle the MAIL server's `DELETE /registry/{swarm_name}` endpoint.
        """
        entry = self.registry.pop(swarm_name, None)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"registry entry not found for swarm `{swarm_name}`",
            )

        if self.registry_path is not None:
            self._save_registry()

        return DeleteRegistryResponse(
            status="success",
            swarm=entry.swarm,
            metadata={},
        )

    async def _fetch_remote_swarm(self, base_url: str) -> MAILRemoteSwarm:
        session = self._require_http_session()

        async with session.get(url=f"{base_url}/swarm") as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=504,
                    detail="failed to get swarm info from remote swarm",
                )
            response_obj = await validate_get_swarm_response(response)

        return MAILRemoteSwarm(
            name=response_obj.swarm.name,
            base_url=base_url,
            protocol_version=response_obj.protocol_version,
            active=response_obj.status == "running",
            last_seen=datetime.now(UTC).isoformat(),
            description=response_obj.swarm.description,
            keywords=response_obj.swarm.keywords,
            metadata=response_obj.swarm.metadata,
        )

    def _require_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            raise RuntimeError("MAIL server HTTP session is not initialized")
        return self._http_session

    def _load_registry(self) -> None:
        if self.registry_path is None or not self.registry_path.exists():
            return

        try:
            persisted_registry = PersistedSwarmRegistry.model_validate_json(
                self.registry_path.read_text()
            )
        except Exception as exc:  # pragma: no cover - defensive error shaping
            raise ValueError(
                f"failed to load registry file at {self.registry_path}: {exc}"
            ) from exc

        self.registry.clear()
        self.registry.update(persisted_registry.entries)

    def _save_registry(self) -> None:
        if self.registry_path is None:
            return

        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        persisted_registry = PersistedSwarmRegistry(
            entries={
                swarm_name: entry
                for swarm_name, entry in self.registry.items()
                if not entry.volatile
            }
        )
        self.registry_path.write_text(
            json.dumps(
                persisted_registry.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
