# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

import argparse
import datetime
import json
import logging
import re
import readline
import shlex
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal, cast

import ujson
from aiohttp import (
    ClientError,
    ClientResponse,
    ClientResponseError,
    ClientSession,
    ClientTimeout,
    ContentTypeError,
)
from openai.types.responses import Response
from rich import console
from rich.syntax import Syntax
from sse_starlette import ServerSentEvent

import mail.utils as utils
from mail.config import ClientConfig
from mail.core.message import MAILInterswarmMessage, MAILMessage
from mail.net.types import (
    GetHealthResponse,
    GetRootResponse,
    GetStatusResponse,
    GetSwarmsDumpResponse,
    GetSwarmsResponse,
    GetWhoamiResponse,
    PostInterswarmMessageResponse,
    PostMessageResponse,
    PostSwarmsLoadResponse,
    PostSwarmsResponse,
)


class MAILClient:
    """
    Asynchronous client for interacting with the MAIL HTTP API.
    """

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        session: ClientSession | None = None,
        config: ClientConfig | None = None,
    ) -> None:
        self.base_url = url.rstrip("/")
        self.api_key = api_key
        if config is None:
            config = ClientConfig()
        self.verbose = config.verbose
        if self.verbose:
            self.logger = logging.getLogger("mail.client")
        else:
            self.logger = logging.getLogger("mailquiet.client")

        timeout_float = float(config.timeout)
        self._timeout = ClientTimeout(total=timeout_float)
        self._session = session
        self._owns_session = session is None
        self._console = console.Console()
        self.user_id = "unknown"
        self.user_role = "unknown"

    def _log_prelude(self) -> str:
        """
        Get the log prelude for the client.
        """
        return f"[{self.user_role}:{self.user_id}@{self.base_url}]"

    async def _register_user_info(self) -> None:
        """
        Attempt to login and fetch user info.
        """
        try:
            self.user_info = await self._request_json("POST", "/auth/login")
            self.user_role = self.user_info["role"]
            self.user_id = self.user_info["id"]
        except Exception as e:
            self.logger.error(f"{self._log_prelude()} error registering user info: {e}")

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
        ignore_auth: bool = False,
    ) -> dict[str, str]:
        """
        Build headers for the HTTP request.
        """
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": f"MAIL-Client/{utils.get_version()} (github.com/charonlabs/mail)",
        }

        if self.api_key and not ignore_auth:
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
        ignore_auth: bool = False,
    ) -> Any:
        """
        Make a request to a remote MAIL swarm via HTTP.
        """
        session = await self._ensure_session()
        url = self._build_url(path)
        self.logger.debug(f"{self._log_prelude()} {method.upper()} {url}")

        try:
            async with session.request(
                method,
                url,
                json=payload,
                headers=self._build_headers(headers, ignore_auth),
            ) as response:
                response.raise_for_status()
                return await self._read_json(response)
        except ClientResponseError as e:
            self.logger.error(
                f"{self._log_prelude()} HTTP request failed with status code {e.status}: '{e.message}'"
            )
            raise RuntimeError(
                f"HTTP request failed with status code {e.status}: '{e.message}'"
            )
        except Exception as e:
            self.logger.error(
                f"{self._log_prelude()} exception during request to remote HTTP, aborting"
            )
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

    async def ping(self) -> GetRootResponse:
        """
        Get basic metadata about the MAIL server (`GET /`).
        """
        return cast(GetRootResponse, await self._request_json("GET", "/"))

    async def get_health(self) -> GetHealthResponse:
        """
        Get the health of the MAIL server (`GET /health`).
        """
        return cast(GetHealthResponse, await self._request_json("GET", "/health"))

    async def update_health(self, status: str) -> GetHealthResponse:
        """
        Update the health of the MAIL server (`POST /health`).
        """
        return cast(
            GetHealthResponse,
            await self._request_json("POST", "/health", payload={"status": status}),
        )

    async def login(self, api_key: str) -> dict[str, Any]:
        """
        Log in to the MAIL server given an API key.
        """
        self.api_key = api_key
        try:
            response = await self._request_json("GET", "/whoami")
            self.user_role = response["role"]
            self.user_id = response["id"]
            return response
        except Exception as e:
            self.api_key = None
            self.logger.error(f"{self._log_prelude()} error logging in: {e}")
            raise RuntimeError(f"MAIL client login failed: {e}")

    async def get_whoami(self) -> GetWhoamiResponse:
        """
        Get the username and role of the caller (`GET /whoami`).
        """
        return cast(GetWhoamiResponse, await self._request_json("GET", "/whoami"))

    async def get_status(self) -> GetStatusResponse:
        """
        Get the status of the MAIL server (`GET /status`).
        """
        return cast(GetStatusResponse, await self._request_json("GET", "/status"))

    async def post_message(
        self,
        body: str,
        subject: str = "New Message",
        msg_type: Literal["request", "response", "broadcast", "interrupt"] = "request",
        *,
        entrypoint: str | None = None,
        show_events: bool = False,
        task_id: str | None = None,
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        **kwargs: Any,
    ) -> PostMessageResponse:
        """
        Queue a user-scoped task, optionally returning runtime events or an SSE stream (`POST /message`).
        """
        payload: dict[str, Any] = {
            "subject": subject,
            "body": body,
            "msg_type": msg_type,
            "entrypoint": entrypoint,
            "show_events": show_events,
            "task_id": task_id,
            "resume_from": resume_from,
            "kwargs": kwargs,
        }

        return cast(
            PostMessageResponse,
            await self._request_json("POST", "/message", payload=payload),
        )

    async def post_message_stream(
        self,
        body: str,
        subject: str = "New Message",
        msg_type: Literal["request", "response", "broadcast", "interrupt"] = "request",
        *,
        entrypoint: str | None = None,
        task_id: str | None = None,
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ServerSentEvent]:
        """
        Queue a user-scoped task, optionally returning runtime events or an SSE stream (`POST /message`).
        """
        session = await self._ensure_session()

        payload: dict[str, Any] = {
            "subject": subject,
            "body": body,
            "msg_type": msg_type,
            "entrypoint": entrypoint,
            "stream": True,
            "task_id": task_id,
            "resume_from": resume_from,
            "kwargs": kwargs,
        }

        url = self._build_url("/message")
        self.logger.debug(f"{self._log_prelude()} POST {url} (stream)")

        try:
            response = await session.post(
                url,
                json=payload,
                headers=self._build_headers({"Accept": "text/event-stream"}),
            )
        except Exception as e:
            self.logger.error(
                f"{self._log_prelude()} exception in POST request, aborting"
            )
            raise RuntimeError(f"MAIL client request failed: {e}")

        try:
            response.raise_for_status()
        except Exception as e:
            self.logger.error(
                f"{self._log_prelude()} exception in POST response, aborting"
            )
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
        try:
            async for chunk in response.content.iter_any():
                buffer += chunk.decode("utf-8", errors="replace")
                if "\r" in buffer:
                    buffer = buffer.replace("\r\n", "\n").replace("\r", "\n")

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
        except (TimeoutError, ClientError) as e:
            self.logger.warning(f"SSE stream interrupted: {e}")
            # Process any remaining complete events in the buffer before returning
            while "\n\n" in buffer:
                raw_event, buffer = buffer.split("\n\n", 1)
                if not raw_event.strip():
                    continue
                event_kwargs = {}
                data_lines = []
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
                data_payload = "\n".join(data_lines) if data_lines else None
                event_kwargs.setdefault("event", "message")
                yield ServerSentEvent(data=data_payload, **event_kwargs)

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
    ) -> PostInterswarmMessageResponse:
        """
        Post an interswarm response to the MAIL server (`POST /interswarm/response`).
        """
        payload = dict(message)

        return cast(
            PostInterswarmMessageResponse,
            await self._request_json(
                "POST",
                "/interswarm/response",
                payload=payload,
            ),
        )

    async def send_interswarm_message(
        self,
        body: str,
        user_token: str,
        subject: str | None = None,
        targets: list[str] | None = None,
        msg_type: str | None = None,
        task_id: str | None = None,
        routing_info: dict[str, Any] | None = None,
        stream: bool | None = None,
        ignore_stream_pings: bool | None = None,
    ) -> PostInterswarmMessageResponse:
        """
        Send an interswarm message to the MAIL server (`POST /interswarm/send`).
        """
        payload: dict[str, Any] = {
            "body": body,
            "user_token": user_token,
        }

        if targets is not None:
            payload["targets"] = targets
        if subject is not None:
            payload["subject"] = subject
        if msg_type is not None:
            payload["msg_type"] = msg_type
        if task_id is not None:
            payload["task_id"] = task_id
        if routing_info is not None:
            payload["routing_info"] = routing_info
        if stream is not None:
            payload["stream"] = stream
        if ignore_stream_pings is not None:
            payload["ignore_stream_pings"] = ignore_stream_pings

        return cast(
            PostInterswarmMessageResponse,
            await self._request_json(
                "POST",
                "/interswarm/message",
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

    async def debug_post_responses(
        self,
        input: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        instructions: str | None = None,
        previous_response_id: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        parallel_tool_calls: bool | None = None,
        **kwargs: Any,
    ) -> Response:
        """
        Post a responses request to the MAIL server in the form of an OpenAI `/responses`-style API call.
        """
        payload: dict[str, Any] = {
            "input": input,
            "tools": tools,
        }

        if instructions is not None:
            payload["instructions"] = instructions
        if previous_response_id is not None:
            payload["previous_response_id"] = previous_response_id
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if parallel_tool_calls is not None:
            payload["parallel_tool_calls"] = parallel_tool_calls
        if kwargs:
            payload["kwargs"] = kwargs

        return Response.model_validate_json(
            await self._request_json("POST", "/responses", payload=payload)
        )

    async def get_tasks(self) -> dict[str, Any]:
        """
        Get the list of tasks for this caller.
        """
        return await self._request_json("GET", "/tasks")

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """
        Get a specific task for this caller.
        """
        return await self._request_json("GET", "/task", payload={"task_id": task_id})


class MAILClientCLI:
    """
    CLI for interacting with the MAIL server.
    """

    def __init__(
        self,
        args: argparse.Namespace,
        config: ClientConfig | None = None,
    ) -> None:
        self.args = args
        self._config = config or ClientConfig()
        self.verbose = args.verbose
        self.client = MAILClient(
            args.url,
            api_key=args.api_key,
            config=self._config,
        )
        self.parser = self._build_parser()
        self._prompt_console = console.Console(force_terminal=True)

        # Initialize readline history
        self._history_file = Path.home() / ".mail_history"
        try:
            readline.read_history_file(self._history_file)
        except (FileNotFoundError, OSError):
            pass
        readline.set_history_length(1000)

    def _build_parser(self) -> argparse.ArgumentParser:
        """
        Build the argument parser for the MAIL client.
        """
        parser = argparse.ArgumentParser(
            prog="",  # to make usage examples work inside the REPL
            description="Interact with a remote MAIL server",
            epilog="For more information, see `README.md` and `docs/`",
        )

        # subparsers for each MAIL command
        subparsers = parser.add_subparsers()

        # command `ping`
        ping_parser = subparsers.add_parser(
            "ping", aliases=["p"], help="ping the MAIL server"
        )
        ping_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /`",
        )
        ping_parser.set_defaults(func=self._ping)

        # command `health`
        health_parser = subparsers.add_parser(
            "health", aliases=["h"], help="get the health of the MAIL server"
        )
        health_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /health`",
        )
        health_parser.set_defaults(func=self._health)

        # command `health-update`
        health_update_parser = subparsers.add_parser(
            "health-update",
            aliases=["hu"],
            help="(admin) update the health of the MAIL server",
        )
        health_update_parser.add_argument(
            "status",
            type=str,
            help="the status of the MAIL server",
        )
        health_update_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `POST /health`",
        )
        health_update_parser.set_defaults(func=self._health_update)

        # command `login`
        login_parser = subparsers.add_parser(
            "login", aliases=["l"], help="log in to the MAIL server"
        )
        login_parser.add_argument(
            "api_key",
            type=str,
            help="the API key to log in with",
        )
        login_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="enable verbose output",
        )
        login_parser.set_defaults(func=self._login)

        # command `logout`
        logout_parser = subparsers.add_parser(
            "logout", aliases=["lo"], help="(user|admin) log out of the MAIL server"
        )
        logout_parser.set_defaults(func=self._logout)

        # command `whoami`
        whoami_parser = subparsers.add_parser(
            "whoami",
            aliases=["me", "id"],
            help="(user|admin) get the username and role of the caller",
        )
        whoami_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /whoami`",
        )
        whoami_parser.set_defaults(func=self._whoami)

        # command `status`
        status_parser = subparsers.add_parser(
            "status",
            aliases=["s"],
            help="(user|admin) view the status of the user runtime within the MAIL server",
        )
        status_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /status`",
        )
        status_parser.set_defaults(func=self._status)

        # command `message`
        message_parser = subparsers.add_parser(
            "message",
            aliases=["m", "msg"],
            help="(user|admin) send a message to the MAIL server",
        )
        message_parser.add_argument(
            "body",
            type=str,
            help="the message to send",
        )
        message_parser.add_argument(
            "-s",
            "--subject",
            type=str,
            required=False,
            default="New Message",
            help="the subject of the message",
        )
        message_parser.add_argument(
            "-t",
            "--msg-type",
            type=str,
            required=False,
            default="request",
            help="the type of the message",
        )
        message_parser.add_argument(
            "-tid",
            "--task-id",
            type=str,
            required=False,
            default=None,
            help="the task ID of the message",
        )
        message_parser.add_argument(
            "-e",
            "--entrypoint",
            type=str,
            required=False,
            default=None,
            help="the agent to send the message to",
        )
        message_parser.add_argument(
            "-se",
            "--show-events",
            action="store_true",
            required=False,
            default=False,
            help="show events",
        )
        message_parser.add_argument(
            "-rf",
            "--resume-from",
            type=str,
            required=False,
            default=None,
            help="the resume from of the message",
        )
        message_parser.add_argument(
            "-k",
            "--kwargs",
            type=json.loads,
            required=False,
            default=f"{{}}",  # noqa: F541
            help="the kwargs of the message",
        )
        message_parser.set_defaults(func=self._message)

        # command `message-stream`
        message_stream_parser = subparsers.add_parser(
            "message-stream",
            aliases=["ms", "msg-s"],
            help="(user|admin) send a message to the MAIL server and stream the response",
        )
        message_stream_parser.add_argument(
            "body",
            type=str,
            help="the message to send",
        )
        message_stream_parser.add_argument(
            "-s",
            "--subject",
            type=str,
            required=False,
            default="New Message",
            help="the subject of the message",
        )
        message_stream_parser.add_argument(
            "-t",
            "--msg-type",
            type=str,
            required=False,
            default="request",
            help="the type of the message",
        )
        message_stream_parser.add_argument(
            "-tid",
            "--task-id",
            type=str,
            required=False,
            default=None,
            help="the task ID of the message",
        )
        message_stream_parser.add_argument(
            "-e",
            "--entrypoint",
            type=str,
            required=False,
            default=None,
            help="the agent to send the message to",
        )
        message_stream_parser.add_argument(
            "-rf",
            "--resume-from",
            type=str,
            required=False,
            default=None,
            help="the resume from of the message",
        )
        message_stream_parser.add_argument(
            "-k",
            "--kwargs",
            type=json.loads,
            required=False,
            default=f"{{}}",  # noqa: F541
            help="the kwargs of the message",
        )
        message_stream_parser.set_defaults(func=self._message_stream)

        # command `message-interswarm`
        message_interswarm_parser = subparsers.add_parser(
            "message-interswarm",
            aliases=["mi", "msg-i"],
            help="(user|admin) send an interswarm message through this MAIL server",
        )
        message_interswarm_parser.add_argument(
            "body",
            type=str,
            help="the message to send",
        )
        message_interswarm_parser.add_argument(
            "targets",
            type=list[str],
            help="the target agent to send the message to",
        )
        message_interswarm_parser.add_argument(
            "user_token",
            type=str,
            help="the user token to send the message with",
        )
        message_interswarm_parser.set_defaults(func=self._message_interswarm)

        # command `swarms-get`
        swarms_get_parser = subparsers.add_parser(
            "swarms-get",
            aliases=["sg", "swarms-g"],
            help="(user|admin) get the list of foreign swarms known by this MAIL server",
        )
        swarms_get_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /swarms`",
        )
        swarms_get_parser.set_defaults(func=self._swarms_get)

        # command `swarm-register`
        swarm_register_parser = subparsers.add_parser(
            "swarm-register",
            aliases=["sr", "swarm-r"],
            help="(admin) register a foreign swarm with the MAIL server",
        )
        swarm_register_parser.add_argument(
            "name",
            type=str,
            help="the name of the swarm",
        )
        swarm_register_parser.add_argument(
            "base_url",
            type=str,
            help="the base URL of the swarm",
        )
        swarm_register_parser.add_argument(
            "auth_token",
            type=str,
            help="the auth token of the swarm",
        )
        swarm_register_parser.add_argument(
            "-V",
            "--volatile",
            action="store_true",
            help="whether the swarm is volatile",
        )
        swarm_register_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `POST /swarms`",
        )
        swarm_register_parser.set_defaults(func=self._swarm_register)

        # command `swarm-dump`
        swarm_dump_parser = subparsers.add_parser(
            "swarm-dump",
            aliases=["sd", "swarm-d"],
            help="(admin) dump the persistent swarm of this MAIL server",
        )
        swarm_dump_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /swarms/dump`",
        )
        swarm_dump_parser.set_defaults(func=self._swarm_dump)

        # command `swarm-load-from-json`
        swarm_load_from_json_parser = subparsers.add_parser(
            "swarm-load-from-json",
            aliases=["sl", "swarm-l"],
            help="(admin) load a swarm from a JSON string",
        )
        swarm_load_from_json_parser.add_argument(
            "swarm_json",
            type=str,
            help="the JSON string to load the swarm from",
        )
        swarm_load_from_json_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `POST /swarms/load`",
        )
        swarm_load_from_json_parser.set_defaults(func=self._swarm_load_from_json)

        # command `responses`
        responses_parser = subparsers.add_parser(
            "responses",
            aliases=["r", "resp"],
            help="(user|admin) (debug only) post a responses request to the MAIL server",
        )
        responses_parser.add_argument(
            "input",
            type=json.loads,
            help="the input to the responses request",
        )
        responses_parser.add_argument(
            "tools",
            type=json.loads,
            help="the tools to the responses request",
        )
        responses_parser.add_argument(
            "-i",
            "--instructions",
            type=str,
            help="the instructions to the responses request",
        )
        responses_parser.add_argument(
            "-pr",
            "--previous-response-id",
            type=str,
            help="the previous response ID to the responses request",
        )
        responses_parser.add_argument(
            "-tc",
            "--tool-choice",
            type=str,
            help="the tool choice to the responses request",
        )
        responses_parser.add_argument(
            "-ptc",
            "--parallel-tool-calls",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="whether to parallel tool calls",
        )
        responses_parser.add_argument(
            "-k",
            "--kwargs",
            type=json.loads,
            help="the kwargs to the responses request",
            default=f"{{}}",  # noqa: F541
        )
        responses_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `POST /responses`",
        )
        responses_parser.set_defaults(func=self._debug_post_responses)

        # command `tasks-get`
        tasks_get_parser = subparsers.add_parser(
            "tasks-get",
            aliases=["tsg", "tasks-g"],
            help="(user|admin) get the list of tasks for this caller",
        )
        tasks_get_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /tasks`",
        )
        tasks_get_parser.set_defaults(func=self._tasks_get)

        # command `task-get`
        task_get_parser = subparsers.add_parser(
            "task-get",
            aliases=["tg", "task-g"],
            help="(user|admin) get a specific task for this caller",
        )
        task_get_parser.add_argument(
            "task_id",
            type=str,
            help="the ID of the task to get",
        )
        task_get_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /task`",
        )
        task_get_parser.set_defaults(func=self._task_get)

        return parser

    async def _ping(self, args: argparse.Namespace) -> None:
        """
        Get the root of the MAIL server.
        """
        try:
            response = await self.client.ping()
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print("pong")
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] pinging: {e}")

    async def _health(self, args: argparse.Namespace) -> None:
        """
        Get the health of the MAIL server.
        """
        try:
            response = await self.client.get_health()
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(
                    f"health: [green]{response['status']}[/green]"
                )
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] getting health: {e}"
            )

    async def _health_update(self, args: argparse.Namespace) -> None:
        """
        Update the health of the MAIL server.
        """
        try:
            response = await self.client.update_health(args.status)
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(
                    f"[green]successfully[/green] updated health to [green]{response['status']}[/green]"
                )
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] updating health: {e}"
            )

    async def _login(self, args: argparse.Namespace) -> None:
        """
        Log in to the MAIL server.
        """
        try:
            response = await self.client.login(args.api_key)
            self.user_role = response["role"]
            self.user_id = response["id"]
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(
                    f"[green]successfully[/green] logged into {self.client.base_url}"
                )
                self.client._console.print(f"> role: [green]{self.user_role}[/green]")
                self.client._console.print(f"> id: [green]{self.user_id}[/green]")
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] logging in: {e}")

    async def _logout(self, args: argparse.Namespace) -> None:
        """
        Log out of the MAIL server.
        """
        if self.user_role not in {"user", "admin"}:
            self.client._console.print(
                "[red bold]error[/red bold] logging out: not currently logged in"
            )
            return

        self.client.api_key = None
        self.api_key = None

        self.client.user_role = "unknown"
        self.client.user_id = "unknown"
        self.user_role = "unknown"
        self.user_id = "unknown"

        self.client._console.print(
            f"[green]successfully[/green] logged out of {self.client.base_url}"
        )

    async def _whoami(self, args: argparse.Namespace) -> None:
        """
        Get the username and role of the caller.
        """
        try:
            response = await self.client.get_whoami()
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(
                    f"role [green]{response['role']}[/green] with ID [green]{response['id']}[/green]"
                )
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] getting whoami: {e}"
            )

    async def _status(self, args: argparse.Namespace) -> None:
        """
        Get the status the user within the MAIL server.
        """
        try:
            response = await self.client.get_status()
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(
                    f"user MAIL {'[green]IS[/green]' if response['user_mail_ready'] else '[red]IS NOT[/red]'} ready"
                )
                self.client._console.print(
                    f"user task {'[green]IS[/green]' if response['user_task_running'] else '[red]IS NOT[/red]'} running"
                )
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] getting status: {e}"
            )

    async def _message(self, args: argparse.Namespace) -> None:
        """
        Post a message to the MAIL server.
        """
        try:
            response = await self.client.post_message(
                body=args.body,
                subject=args.subject or "New Message",
                msg_type=args.msg_type,
                entrypoint=args.entrypoint,
                show_events=args.show_events,
                task_id=args.task_id,
                resume_from=args.resume_from,
                **args.kwargs,
            )
            self.client._console.print(
                json.dumps(response, indent=2, ensure_ascii=False)
            )
            self._print_embedded_xml(response)
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] posting message: {e}"
            )

    async def _message_stream(self, args: argparse.Namespace) -> None:
        """
        Post a message to the MAIL server and stream the response.
        """
        try:
            response = await self.client.post_message_stream(
                body=args.body,
                subject=args.subject or "New Message",
                msg_type=args.msg_type,
                entrypoint=args.entrypoint,
                task_id=args.task_id,
                resume_from=args.resume_from,
                **args.kwargs,
            )
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] connecting to server: {e}"
            )
            return

        try:
            async for event in response:
                try:
                    event_dict = {
                        "event": event.event,
                        "data": event.data,
                    }
                    self.client._console.print(self._strip_event(event_dict))
                except Exception as e:
                    self.client._console.print(
                        f"[yellow]warning: failed to process event: {e}[/yellow]"
                    )
                    continue
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] streaming response: {e}"
            )

    async def _swarms_get(self, args: argparse.Namespace) -> None:
        """
        Get the swarms of the MAIL server.
        """
        try:
            response = await self.client.get_swarms()
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(f"found {len(response['swarms'])} swarms:")
                for swarm in response["swarms"]:
                    self.client._console.print(
                        f"{swarm['swarm_name']}@{swarm['base_url']}"
                    )
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] getting swarms: {e}"
            )

    async def _swarm_register(self, args: argparse.Namespace) -> None:
        """
        Register a swarm with the MAIL server.
        """
        try:
            response = await self.client.register_swarm(
                args.name,
                args.base_url,
                auth_token=args.auth_token,
                volatile=args.volatile,
                metadata=None,
            )
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(f"swarm {args.name} registered")
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] registering swarm: {e}"
            )

    async def _swarm_dump(self, args: argparse.Namespace) -> None:
        """
        Dump the swarm of the MAIL server.
        """
        try:
            response = await self.client.dump_swarm()
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(f"swarm '{response['swarm_name']}' dumped")
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] dumping swarm: {e}")

    async def _message_interswarm(self, args: argparse.Namespace) -> None:
        """
        Send an interswarm message to the MAIL server.
        """
        try:
            response = await self.client.send_interswarm_message(
                args.body, args.targets, args.user_token
            )
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] sending interswarm message: {e}"
            )

    async def _swarm_load_from_json(self, args: argparse.Namespace) -> None:
        """
        Load a swarm from a JSON string.
        """
        try:
            response = await self.client.load_swarm_from_json(args.swarm_json)
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(f"swarm '{response['swarm_name']}' loaded")
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] loading swarm from JSON: {e}"
            )

    async def _debug_post_responses(self, args: argparse.Namespace) -> None:
        """
        Post a responses request to the MAIL server in the form of an OpenAI `/responses`-style API call.
        """
        try:
            tool_choice = args.tool_choice
            if tool_choice is not None:
                try:
                    tool_choice = json.loads(tool_choice)
                except (TypeError, json.JSONDecodeError):
                    pass

            response = await self.client.debug_post_responses(
                args.input,
                args.tools,
                args.instructions,
                args.previous_response_id,
                tool_choice,
                args.parallel_tool_calls,
                **(args.kwargs or {}),
            )

            if args.verbose:
                self.client._console.print(response.model_dump())
            else:
                self.client._console.print(f"response ID: [green]{response.id}[/green]")
                self.client._console.print(
                    f"response created at: [green]{response.created_at}[/green]"
                )
                self.client._console.print(
                    f"response model: [green]{response.model}[/green]"
                )
                self.client._console.print(
                    f"response object: [green]{response.object}[/green]"
                )
                self.client._console.print(
                    f"response tools: [green]{response.tools}[/green]"
                )
                self.client._console.print(
                    f"response output: [green]{response.output}[/green]"
                )
                self.client._console.print(
                    f"response parallel tool calls: [green]{response.parallel_tool_calls}[/green]"
                )
                self.client._console.print(
                    f"response tool choice: [green]{response.tool_choice}[/green]"
                )
        except Exception as e:
            self.client._console.print(
                f"[red bold]error[/red bold] posting responses: {e}"
            )

    async def _tasks_get(self, args: argparse.Namespace) -> None:
        """
        Get the list of tasks for this caller.
        """
        try:
            response = await self.client.get_tasks()
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(f"found {len(response)} tasks:")
                for task_id, task in response.items():
                    self.client._console.print(
                        f"{task_id} - completed: {task.get('completed', 'unknown')}"
                    )
                    self.client._console.print("  - events:")
                    for event in self._strip_events(task.get("events", "unknown")):
                        self.client._console.print(event)
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] getting tasks: {e}")

    async def _task_get(self, args: argparse.Namespace) -> None:
        """
        Get a specific task for this caller.
        """
        try:
            response = await self.client.get_task(args.task_id)
            if args.verbose:
                self.client._console.print(json.dumps(response, indent=2))
            else:
                self.client._console.print(
                    f"task '{response['task_id']}' - completed: {response.get('completed', 'unknown')}"
                )
                self.client._console.print("  - events:")
                for event in self._strip_events(response.get("events", "unknown")):
                    self.client._console.print(event)
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] getting task: {e}")

    def _strip_event(self, event: Any) -> str:
        """
        Strip the event from the task.
        """
        if isinstance(event, str):
            return event

        event_type = event.get("event")
        data = event.get("data")
        if data is None:
            return "unknown"
        payload: Any = data
        if isinstance(payload, str):
            if payload == "":
                return "unknown"

            try:
                payload = ujson.loads(payload)
            except (ujson.JSONDecodeError, ValueError):
                # Fallback for single-quoted dict strings emitted by some runtimes.
                payload = payload.replace('"', "::tmp::")
                payload = payload.replace("'", '"')
                payload = payload.replace("::tmp::", "'")
                payload = payload.replace("None", '"unknown"')
                try:
                    payload = ujson.loads(payload)
                except (ujson.JSONDecodeError, ValueError):
                    if event_type == "task_complete":
                        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
                        return f"\t{timestamp} - {payload}"
                    return payload

        if not isinstance(payload, dict):
            return "unknown"

        timestamp = payload.get("timestamp", "unknown")
        description = payload.get("description")
        if not description:
            description = payload.get("response")
        if not description:
            description = "unknown (possible ping)"

        return f"\t{timestamp} - {description}"

    def _strip_events(self, events: Any) -> list[str]:
        """
        Strip the events from the task.
        """
        if isinstance(events, str):
            if events == "unknown":
                return []
            return [events]

        events_list: list[str] = []
        for event in events:
            events_list.append(self._strip_event(event))
        return events_list

    def _print_preamble(self) -> None:
        """
        Print the preamble for the MAIL client.
        """
        self.client._console.print(
            f"[bold]MAIL CLIent v[cyan]{utils.get_version()}[/cyan][/bold]"
        )
        self.client._console.print(
            "Enter [cyan]`help`[/cyan] for help and [cyan]`exit`[/cyan] to quit"
        )
        self.client._console.print("==========")

    def _repl_input_string(
        self,
        user_role: str,
        user_id: str,
        base_url: str,
    ) -> str:
        """
        Get the input string for the REPL.
        """
        base_url = base_url.removeprefix("http://")
        base_url = base_url.removeprefix("https://")
        # truncate the user ID if it's longer than 8 characters
        if len(user_id) > 8:
            user_id = f"{user_id[:4]}...{user_id[-4:]}"

        return f"[cyan bold]mail[/cyan bold]::[green bold]{user_role}:{user_id}@{base_url}[/green bold]> "

    @staticmethod
    def _readline_safe_prompt(prompt: str) -> str:
        """
        Wrap ANSI codes so readline ignores them when computing prompt length.
        """
        ansi_pattern = re.compile(r"(\x1b\[[0-9;?]*[ -/]*[@-~])")
        return ansi_pattern.sub(lambda match: f"\001{match.group(1)}\002", prompt)

    def _render_prompt(self, prompt_markup: str) -> str:
        """
        Render Rich markup to ANSI and make it safe for readline editing.
        """
        with self._prompt_console.capture() as capture:
            self._prompt_console.print(prompt_markup, end="")
        rendered = capture.get().rstrip("\n")
        return self._readline_safe_prompt(rendered)

    async def run(
        self,
        attempt_login: bool = True,
    ) -> None:
        """
        Run the MAIL client as a REPL in the terminal.
        """
        if attempt_login:
            try:
                whoami = await self.client.get_whoami()
                self.client._console.print(
                    f"[green]successfully[/green] logged into {self.client.base_url}"
                )
                self.client._console.print(f"> role: [green]{whoami['role']}[/green]")
                self.client._console.print(f"> id: [green]{whoami['id']}[/green]")
            except Exception as e:
                self.client._console.print(
                    "[yellow]warning[/yellow]: unable to determine identity via /whoami"
                )
                self.client._console.print(f"> error: {e}")
                self.client._console.print(
                    "> NOTE: your client will be connected to the server but will not be logged in"
                )
                self.client._console.print(
                    "> NOTE: you can log in by running `login {YOUR_API_KEY}`"
                )
                self.user_role = "unknown"
                self.user_id = "unknown"
            else:
                self.user_id = whoami.get("id", "unknown")
                self.user_role = whoami.get("role", "unknown")
        else:
            self.user_id = "unknown"
            self.user_role = "unknown"
        self.base_url = self.client.base_url

        self._print_preamble()

        while True:
            try:
                prompt_markup = self._repl_input_string(
                    self.user_role, self.user_id, self.base_url
                )
                raw_command = self.client._console.input(prompt_markup)
            except EOFError:
                self.client._console.print()
                break
            except KeyboardInterrupt:
                self.client._console.print()
                continue

            if not raw_command.strip():
                continue

            try:
                tokens = shlex.split(raw_command)
            except ValueError as exc:
                self.client._console.print(
                    f"[red bold]error[/red bold] parsing command: {exc}"
                )
                continue

            command = tokens[0]

            if command in {"exit", "quit"}:
                break
            if command in {"help", "?"}:
                self.parser.print_help()
                continue

            try:
                args = self.parser.parse_args(tokens)
            except SystemExit:
                continue

            func = getattr(args, "func", None)
            if func is None:
                self.parser.print_help()
                continue

            await func(args)

        # Save readline history on exit
        try:
            readline.write_history_file(self._history_file)
        except OSError:
            pass

    @staticmethod
    def _collect_xml_strings(candidate: Any) -> list[str]:
        """
        Recursively gather XML-like strings from nested data.
        """

        collected_set: set[str] = set()

        def _walk(node: Any) -> None:
            if isinstance(node, str):
                snippet = node.strip()
                if "<" in snippet and ">" in snippet:
                    start = snippet.find("<")
                    end = snippet.rfind(">")
                    if start != -1 and end != -1 and start < end:
                        candidate = snippet[start : end + 1]
                        candidate = (
                            candidate.replace("\\n", "")
                            .replace("\\t", "\t")
                            .replace("[\\'", "")
                            .replace("\\']", "")
                        )
                        collected_set.add(candidate)
                return
            if hasattr(node, "description"):
                try:
                    _walk(getattr(node, "description"))
                except Exception:
                    pass
                return
            if isinstance(node, dict):
                for value in node.values():
                    _walk(value)
                return
            if isinstance(node, list | tuple | set):
                for value in node:
                    _walk(value)

        _walk(candidate)
        return list(collected_set)

    @staticmethod
    def _pretty_format_xml(xml_text: str) -> str | None:
        try:
            from xml.dom import minidom

            parsed = minidom.parseString(xml_text)
            pretty = parsed.toprettyxml(indent="  ", encoding="utf-8")
        except Exception:
            return None

        try:
            return pretty.decode("utf-8").strip()
        except AttributeError:
            return pretty.strip().decode("utf-8")

    def _print_embedded_xml(self, payload: Any) -> None:
        for snippet in self._collect_xml_strings(payload):
            pretty = self._pretty_format_xml(snippet)
            if pretty:
                self.client._console.print(Syntax(pretty, "xml"))
