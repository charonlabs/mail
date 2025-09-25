# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from aiohttp import (
    ClientResponse,
    ClientSession,
    ClientTimeout,
    ContentTypeError,
)
from sse_starlette import ServerSentEvent

from mail.core.message import MAILInterswarmMessage, MAILMessage
from mail.net.types import (
    GetHealthResponse,
    GetRootResponse,
    GetStatusResponse,
    GetSwarmsDumpResponse,
    GetSwarmsResponse,
    PostInterswarmResponseResponse,
    PostInterswarmSendResponse,
    PostMessageResponse,
    PostSwarmsLoadResponse,
    PostSwarmsResponse,
)

logger = logging.getLogger("mail.client")


class MAILClient:
    """
    Asynchronous client for interacting with the MAIL HTTP API.
    """

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        timeout: ClientTimeout | float | None = 60.0,
        session: ClientSession | None = None,
    ) -> None:
        self.base_url = url.rstrip("/")
        self.api_key = api_key
        if isinstance(timeout, ClientTimeout) or timeout is None:
            self._timeout = timeout
        else:
            self._timeout = ClientTimeout(total=float(timeout))
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> MAILClient:
        await self._ensure_session()
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
        self._session = None

    async def _ensure_session(self) -> ClientSession:
        """
        Ensure a session exists by creating one if it doesn't.
        """
        if self._session is None:
            session_kwargs: dict[str, Any] = {}
            if self._timeout is not None:
                session_kwargs["timeout"] = self._timeout
            self._session = ClientSession(**session_kwargs)

        return self._session

    def _build_url(self, path: str) -> str:
        """
        Build the URL for the HTTP request, given `self.base_url` and `path`.
        """
        return f"{self.base_url}/{path.lstrip('/')}"

    def _build_headers(
        self,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """
        Build headers for the HTTP request.
        """
        headers: dict[str, str] = {"Accept": "application/json"}

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update(extra)

        return headers

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """
        Make a request to a remote MAIL swarm via HTTP.
        """
        session = await self._ensure_session()
        url = self._build_url(path)
        logger.debug("%s %s", method.upper(), url)

        try:
            async with session.request(
                method,
                url,
                json=payload,
                headers=self._build_headers(headers),
            ) as response:
                response.raise_for_status()
                return await self._read_json(response)
        except Exception as e:
            raise RuntimeError(f"MAIL client request failed: {e}")

    @staticmethod
    async def _read_json(response: ClientResponse) -> Any:
        """
        Read the JSON body from the HTTP response.
        """
        try:
            return await response.json()
        except ContentTypeError as exc:
            text = await response.text()
            raise ValueError(
                f"expected JSON response but received content with type '{response.content_type}': {text}"
            ) from exc

    async def get_root(self) -> GetRootResponse:
        """
        Get basic metadata about the MAIL server (`GET /`).
        """
        return cast(GetRootResponse, await self._request_json("GET", "/"))

    async def get_status(self) -> GetStatusResponse:
        """
        Get the status of the MAIL server (`GET /status`).
        """
        return cast(GetStatusResponse, await self._request_json("GET", "/status"))

    async def post_message(
        self,
        message: str,
        *,
        entrypoint: str | None = None,
        show_events: bool = False,
    ) -> PostMessageResponse:
        """
        Queue a user-scoped task, optionally returning runtime events or an SSE stream (`POST /message`).
        """
        payload: dict[str, Any] = {"message": message}

        if entrypoint:
            payload["entrypoint"] = entrypoint
        if show_events:
            payload["show_events"] = True

        return cast(
            PostMessageResponse,
            await self._request_json("POST", "/message", payload=payload),
        )

    async def post_message_stream(
        self,
        message: str,
        *,
        entrypoint: str | None = None,
    ) -> AsyncIterator[ServerSentEvent]:
        """
        Queue a user-scoped task, optionally returning runtime events or an SSE stream (`POST /message`).
        """
        session = await self._ensure_session()

        payload: dict[str, Any] = {
            "message": message,
            "stream": True,
        }

        if entrypoint:
            payload["entrypoint"] = entrypoint
        url = self._build_url("/message")
        logger.debug("POST %s (stream)", url)

        try:
            response = await session.post(
                url,
                json=payload,
                headers=self._build_headers({"Accept": "text/event-stream"}),
            )
        except Exception as e:
            raise RuntimeError(f"MAIL client request failed: {e}")

        try:
            response.raise_for_status()
        except Exception as e:
            response.close()
            raise RuntimeError(f"MAIL client request failed: {e}") from e

        async def _event_stream() -> AsyncIterator[ServerSentEvent]:
            try:
                async for event in self._iterate_sse(response):
                    yield event
            finally:
                response.close()

        return _event_stream()

    async def _iterate_sse(
        self,
        response: ClientResponse,
    ) -> AsyncIterator[ServerSentEvent]:
        """
        Minimal SSE parser to stitch chunked bytes into ServerSentEvent instances.
        """
        buffer = ""
        async for chunk in response.content.iter_any():
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buffer:
                raw_event, buffer = buffer.split("\n\n", 1)
                if not raw_event.strip():
                    continue
                event_kwargs: dict[str, Any] = {}
                data_lines: list[str] = []
                for line in raw_event.splitlines():
                    if not line or line.startswith(":"):
                        continue
                    field, _, value = line.partition(":")
                    value = value.lstrip(" ")
                    if field == "data":
                        data_lines.append(value)
                    elif field == "event":
                        event_kwargs["event"] = value
                    elif field == "id":
                        event_kwargs["id"] = value
                    elif field == "retry":
                        try:
                            event_kwargs["retry"] = int(value)
                        except ValueError:
                            pass
                data_payload = "\n".join(data_lines) if data_lines else None
                event_kwargs.setdefault("event", "message")
                yield ServerSentEvent(data=data_payload, **event_kwargs)

    async def get_health(self) -> GetHealthResponse:
        """
        Get the health of the MAIL server (`GET /health`).
        """
        return cast(GetHealthResponse, await self._request_json("GET", "/health"))

    async def get_swarms(self) -> GetSwarmsResponse:
        """
        Get the swarms of the MAIL server (`GET /swarms`).
        """
        return cast(GetSwarmsResponse, await self._request_json("GET", "/swarms"))

    async def register_swarm(
        self,
        name: str,
        base_url: str,
        *,
        auth_token: str | None = None,
        volatile: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> PostSwarmsResponse:
        """
        Register a swarm with the MAIL server (`POST /swarms`).
        """
        payload: dict[str, Any] = {
            "name": name,
            "base_url": base_url,
            "volatile": volatile,
        }

        if auth_token is not None:
            payload["auth_token"] = auth_token
        if metadata is not None:
            payload["metadata"] = metadata

        return cast(
            PostSwarmsResponse,
            await self._request_json("POST", "/swarms", payload=payload),
        )

    async def dump_swarm(self) -> GetSwarmsDumpResponse:
        """
        Dump the swarm of the MAIL server (`GET /swarms/dump`).
        """
        return cast(
            GetSwarmsDumpResponse,
            await self._request_json("GET", "/swarms/dump"),
        )

    async def post_interswarm_message(
        self,
        message: MAILInterswarmMessage,
    ) -> MAILMessage:
        """
        Post an interswarm message to the MAIL server (`POST /interswarm/message`).
        """
        payload = dict(message)

        response = await self._request_json(
            "POST",
            "/interswarm/message",
            payload=payload,
        )

        return cast(MAILMessage, response)

    async def post_interswarm_response(
        self,
        message: MAILMessage,
    ) -> PostInterswarmResponseResponse:
        """
        Post an interswarm response to the MAIL server (`POST /interswarm/response`).
        """
        payload = dict(message)

        return cast(
            PostInterswarmResponseResponse,
            await self._request_json(
                "POST",
                "/interswarm/response",
                payload=payload,
            ),
        )

    async def send_interswarm_message(
        self,
        target_agent: str,
        message: str,
        user_token: str,
    ) -> PostInterswarmSendResponse:
        """
        Send an interswarm message to the MAIL server (`POST /interswarm/send`).
        """
        payload = {
            "target_agent": target_agent,
            "message": message,
            "user_token": user_token,
        }

        return cast(
            PostInterswarmSendResponse,
            await self._request_json(
                "POST",
                "/interswarm/send",
                payload=payload,
            ),
        )

    async def load_swarm_from_json(
        self,
        swarm_json: str,
    ) -> PostSwarmsLoadResponse:
        """
        Load a swarm from a JSON document (`POST /swarms/load`).
        """
        payload = {"json": swarm_json}

        return cast(
            PostSwarmsLoadResponse,
            await self._request_json(
                "POST",
                "/swarms/load",
                payload=payload,
            ),
        )
