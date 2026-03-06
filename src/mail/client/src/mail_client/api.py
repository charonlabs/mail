# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import httpx
from mail_protocol import Metadata
from mail_protocol.core.address import MAILAddress
from mail_protocol.core.message import MAILMessageType
from mail_protocol.interswarm import MAILInterswarmMessage
from mail_protocol.network.requests import (
    PostInterswarmMessageRequest,
    PostMessageRequest,
    PostRegistryRequest,
)
from mail_protocol.network.responses import (
    DeleteRegistryResponse,
    GetRegistryResponse,
    GetRootResponse,
    GetSwarmResponse,
    PostInterswarmMessageResponse,
    PostMessageResponse,
    PostRegistryResponse,
)
from pydantic import ValidationError

from mail_client.types import MAILRequestError, MAILResponseError
from mail_client.utils import get_version


class MAILClient:
    """
    A basic, synchronous client API for interacting with MAIL servers.
    """
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "User-Agent": f"MAIL-Client/{get_version()} (github.com/charonlabs/mail)",
            },
        )
        if self.api_key:
            self.client.headers["Authorization"] = f"Bearer {self.api_key}"

    def ping(self) -> GetRootResponse:
        """
        Get the root of the MAIL server.
        Basic server information and metadata.
        """
        response = self.client.get("/")

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )

        try:
            return GetRootResponse.model_validate_json(response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    def get_swarm(self) -> GetSwarmResponse:
        """
        Get the swarm of the MAIL server.
        """
        response = self.client.get("/swarm")

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
        
        try:
            return GetSwarmResponse.model_validate_json(response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    def get_registry(self) -> GetRegistryResponse:
        """
        Get the registry of remote swarms for this MAIL server.
        """
        response = self.client.get("/registry")

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
            
        try:
            return GetRegistryResponse.model_validate_json(response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    def register_swarm(
        self,
        base_url: str,
        api_key_ref: str,
        *,
        public: bool = True,
        volatile: bool = True,
        metadata: Metadata = {},
    ) -> PostRegistryResponse:
        """
        Register a remote swarm with this MAIL server.
        """
        response = self.client.post("/registry", json=PostRegistryRequest(
            base_url=base_url,
            api_key_ref=api_key_ref,
            public=public,
            volatile=volatile,
            metadata=metadata,
        ))

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
            
        try:
            return PostRegistryResponse.model_validate_json(response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    def deregister_swarm(
        self,
        swarm_name: str,
    ) -> DeleteRegistryResponse:
        """
        Deregister a remote swarm from this MAIL server.
        """
        response = self.client.delete(f"/registry/{swarm_name}")

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
            
        try:
            return DeleteRegistryResponse.model_validate_json(response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    def post_message(
        self,
        task_id: str,
        msg_type: MAILMessageType,
        subject: str,
        body: str,
        recipients: list[MAILAddress],
        metadata: Metadata = {},
    ) -> PostMessageResponse:
        """
        Post a message to the MAIL server.
        """
        response = self.client.post("/message", json=PostMessageRequest(
            task_id=task_id,
            msg_type=msg_type,
            subject=subject,
            body=body,
            recipients=recipients,
            metadata=metadata,
        ))

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
            
        try:
            return PostMessageResponse.model_validate_json(response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    def post_interswarm_message(
        self,
        message: MAILInterswarmMessage,
        metadata: Metadata = {},
    ) -> PostInterswarmMessageResponse:
        """
        Post an interswarm message to the MAIL server.
        """
        response = self.client.post("/interswarm/message", json=PostInterswarmMessageRequest(
            message=message,
            metadata=metadata,
        ))

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
        
        try:
            return PostInterswarmMessageResponse.model_validate_json(response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")


class MAILAsyncClient:
    """
    A basic, asynchronous client API for interacting with MAIL servers.
    """
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "User-Agent": f"MAIL-Client/{get_version()} (github.com/charonlabs/mail)",
            },
        )
        if self.api_key:
            self.client.headers["Authorization"] = f"Bearer {self.api_key}"

    async def ping(self) -> GetRootResponse:
        """
        Get the root of the MAIL server.
        Basic server information and metadata.
        """
        response = await self.client.get("/")

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )

        try:
            return GetRootResponse.model_validate_json(await response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    async def get_swarm(self) -> GetSwarmResponse:
        """
        Get the swarm of the MAIL server.
        """
        response = await self.client.get("/swarm")

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
            
        try:
            return GetSwarmResponse.model_validate_json(await response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    async def get_registry(self) -> GetRegistryResponse:
        """
        Get the registry of remote swarms for this MAIL server.
        """
        response = await self.client.get("/registry")

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
            
        try:
            return GetRegistryResponse.model_validate_json(await response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    async def register_swarm(
        self,
        base_url: str,
        api_key_ref: str,
        *,
        public: bool = True,
        volatile: bool = True,
        metadata: Metadata = {},
    ) -> PostRegistryResponse:
        """
        Register a remote swarm with this MAIL server.
        """
        response = await self.client.post("/registry", json=PostRegistryRequest(
            base_url=base_url,
            api_key_ref=api_key_ref,
            public=public,
            volatile=volatile,
            metadata=metadata,
        ))

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
        try:
            return PostRegistryResponse.model_validate_json(await response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    async def deregister_swarm(
        self,
        swarm_name: str,
    ) -> DeleteRegistryResponse:
        """
        Deregister a remote swarm from this MAIL server.
        """
        response = await self.client.delete(f"/registry/{swarm_name}")
        
        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
            
        try:
            return DeleteRegistryResponse.model_validate(await response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    async def post_message(
        self,
        task_id: str,
        msg_type: MAILMessageType,
        subject: str,
        body: str,
        recipients: list[MAILAddress],
        metadata: Metadata = {},
    ) -> PostMessageResponse:
        """
        Post a message to the MAIL server.
        """
        response = await self.client.post("/message", json=PostMessageRequest(
            task_id=task_id,
            msg_type=msg_type,
            subject=subject,
            body=body,
            recipients=recipients,
            metadata=metadata,
        ))

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
            
        try:
            return PostMessageResponse.model_validate(await response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")

    async def post_interswarm_message(
        self,
        message: MAILInterswarmMessage,
        metadata: Metadata = {},
    ) -> PostInterswarmMessageResponse:
        """
        Post an interswarm message to the MAIL server.
        """
        response = await self.client.post("/interswarm/message", json=PostInterswarmMessageRequest(
            message=message,
            metadata=metadata,
        ))

        if response.status_code != 200:
            raise MAILRequestError(
                status_code=response.status_code,
                detail=response.text,
                request=response.request,
                response=response,
            )
            
        try:
            return PostInterswarmMessageResponse.model_validate(await response.json())
        except ValidationError as e:
            raise MAILResponseError(detail=f"failed to validate response body: {e}")