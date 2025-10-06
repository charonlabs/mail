# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shlex
from collections.abc import AsyncIterator
from typing import Any, Literal, cast

from aiohttp import (
    ClientResponse,
    ClientSession,
    ClientTimeout,
    ContentTypeError,
)
from rich import console
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
    PostInterswarmResponseResponse,
    PostInterswarmSendResponse,
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

    async def _register_user_info(self) -> None:
        """
        Attempt to login and fetch user info.
        """
        try:
            self.username = await self._request_json("POST", "/auth/login")
            self.user_info = await self._request_json("GET", "/auth/check")
        except Exception as e:
            self.logger.error(f"error registering user info: {e}")

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
        self.logger.debug(f"{method.upper()} {url}")

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
            self.logger.error("exception during request to remote HTTP, aborting")
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
        self.logger.debug(f"POST {url} (stream)")

        try:
            response = await session.post(
                url,
                json=payload,
                headers=self._build_headers({"Accept": "text/event-stream"}),
            )
        except Exception as e:
            self.logger.error("exception in POST request, aborting")
            raise RuntimeError(f"MAIL client request failed: {e}")

        try:
            response.raise_for_status()
        except Exception as e:
            self.logger.error("exception in POST response, aborting")
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
        body: str,
        user_token: str,
        subject: str | None = None,
        targets: list[str] | None = None,
        msg_type: str | None = None,
        task_id: str | None = None,
        routing_info: dict[str, Any] | None = None,
        stream: bool | None = None,
        ignore_stream_pings: bool | None = None,
    ) -> PostInterswarmSendResponse:
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

        # command `get-root`
        get_root_parser = subparsers.add_parser(
            "get-root", help="get the root of the MAIL server"
        )
        get_root_parser.set_defaults(func=self._get_root)

        # command `get-whoami`
        get_whoami_parser = subparsers.add_parser(
            "get-whoami", help="get the username and role of the caller"
        )
        get_whoami_parser.set_defaults(func=self._get_whoami)

        # command `post-message`
        post_message_parser = subparsers.add_parser(
            "post-message", help="send a message to the MAIL server"
        )
        post_message_parser.add_argument(
            "body",
            type=str,
            help="the message to send",
        )
        post_message_parser.add_argument(
            "-s",
            "--subject",
            type=str,
            required=False,
            default="New Message",
            help="the subject of the message",
        )
        post_message_parser.add_argument(
            "-t",
            "--msg-type",
            type=str,
            required=False,
            default="request",
            help="the type of the message",
        )
        post_message_parser.add_argument(
            "-tid",
            "--task-id",
            type=str,
            required=False,
            default=None,
            help="the task ID of the message",
        )
        post_message_parser.add_argument(
            "-e",
            "--entrypoint",
            type=str,
            required=False,
            default=None,
            help="the agent to send the message to",
        )
        post_message_parser.add_argument(
            "-se",
            "--show-events",
            action="store_true",
            required=False,
            default=False,
            help="show events",
        )
        post_message_parser.add_argument(
            "-rf",
            "--resume-from",
            type=str,
            required=False,
            default=None,
            help="the resume from of the message",
        )
        post_message_parser.add_argument(
            "-k",
            "--kwargs",
            type=json.loads,
            required=False,
            default=f"{{}}",  # noqa: F541
            help="the kwargs of the message",
        )
        post_message_parser.set_defaults(func=self._post_message)

        # command `post-message-stream`
        post_message_stream_parser = subparsers.add_parser(
            "post-message-stream",
            help="send a message to the MAIL server and stream the response",
        )
        post_message_stream_parser.add_argument(
            "body",
            type=str,
            help="the message to send",
        )
        post_message_stream_parser.add_argument(
            "-s",
            "--subject",
            type=str,
            required=False,
            default="New Message",
            help="the subject of the message",
        )
        post_message_stream_parser.add_argument(
            "-t",
            "--msg-type",
            type=str,
            required=False,
            default="request",
            help="the type of the message",
        )
        post_message_stream_parser.add_argument(
            "-tid",
            "--task-id",
            type=str,
            required=False,
            default=None,
            help="the task ID of the message",
        )
        post_message_stream_parser.add_argument(
            "-e",
            "--entrypoint",
            type=str,
            required=False,
            default=None,
            help="the agent to send the message to",
        )
        post_message_stream_parser.add_argument(
            "-rf",
            "--resume-from",
            type=str,
            required=False,
            default=None,
            help="the resume from of the message",
        )
        post_message_stream_parser.add_argument(
            "-k",
            "--kwargs",
            type=json.loads,
            required=False,
            default=f"{{}}",  # noqa: F541
            help="the kwargs of the message",
        )
        post_message_stream_parser.set_defaults(func=self._post_message_stream)

        # command `get-health`
        get_health_parser = subparsers.add_parser(
            "get-health", help="get the health of the MAIL server"
        )
        get_health_parser.set_defaults(func=self._get_health)

        # command `get-swarms`
        get_swarms_parser = subparsers.add_parser(
            "get-swarms", help="get the swarms of the MAIL server"
        )
        get_swarms_parser.set_defaults(func=self._get_swarms)

        # command `register-swarm`
        register_swarm_parser = subparsers.add_parser(
            "register-swarm", help="register a swarm with the MAIL server"
        )
        register_swarm_parser.add_argument(
            "-n",
            "--name",
            type=str,
            help="the name of the swarm",
        )
        register_swarm_parser.add_argument(
            "-bu",
            "--base-url",
            type=str,
            help="the base URL of the swarm",
        )
        register_swarm_parser.add_argument(
            "-at",
            "--auth-token",
            type=str,
            required=False,
            help="the auth token of the swarm",
        )
        register_swarm_parser.add_argument(
            "-v",
            "--volatile",
            type=bool,
            required=False,
            default=False,
            help="whether the swarm is volatile",
        )
        register_swarm_parser.set_defaults(func=self._register_swarm)

        # command `dump-swarm`
        dump_swarm_parser = subparsers.add_parser(
            "dump-swarm", help="dump the swarm of the MAIL server"
        )
        dump_swarm_parser.set_defaults(func=self._dump_swarm)

        # command `send-interswarm-message`
        send_interswarm_message_parser = subparsers.add_parser(
            "send-interswarm-message",
            help="send an interswarm message to the MAIL server",
        )
        send_interswarm_message_parser.add_argument(
            "--body",
            type=str,
            help="the message to send",
        )
        send_interswarm_message_parser.add_argument(
            "--targets",
            type=list[str],
            help="the target agent to send the message to",
        )
        send_interswarm_message_parser.add_argument(
            "--user-token",
            type=str,
            help="the user token to send the message with",
        )
        send_interswarm_message_parser.set_defaults(func=self._send_interswarm_message)

        # command `load-swarm-from-json`
        load_swarm_from_json_parser = subparsers.add_parser(
            "load-swarm-from-json", help="load a swarm from a JSON document"
        )
        load_swarm_from_json_parser.add_argument(
            "--swarm-json",
            type=str,
            help="the JSON document to load the swarm from",
        )
        load_swarm_from_json_parser.set_defaults(func=self._load_swarm_from_json)

        return parser

    async def _get_root(self, _args: argparse.Namespace) -> None:
        """
        Get the root of the MAIL server.
        """
        try:
            response = await self.client.get_root()
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] getting root: {e}")

    async def _get_whoami(self, _args: argparse.Namespace) -> None:
        """
        Get the username and role of the caller.
        """
        try:
            response = await self.client.get_whoami()
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] getting whoami: {e}")

    async def _post_message(self, args: argparse.Namespace) -> None:
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
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] posting message: {e}")

    async def _post_message_stream(self, args: argparse.Namespace) -> None:
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
            async for event in response:
                parsed_event = {
                    "event": event.event,
                    "data": event.data,
                }
                self.client._console.print(json.dumps(parsed_event, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] posting message: {e}")

    async def _get_health(self, _args: argparse.Namespace) -> None:
        """
        Get the health of the MAIL server.
        """
        try:
            response = await self.client.get_health()
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] getting health: {e}")

    async def _get_swarms(self, _args: argparse.Namespace) -> None:
        """
        Get the swarms of the MAIL server.
        """
        try:
            response = await self.client.get_swarms()
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] getting swarms: {e}")

    async def _register_swarm(self, args: argparse.Namespace) -> None:
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
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] registering swarm: {e}")

    async def _dump_swarm(self, _args: argparse.Namespace) -> None:
        """
        Dump the swarm of the MAIL server.
        """
        try:
            response = await self.client.dump_swarm()
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] dumping swarm: {e}")

    async def _send_interswarm_message(self, args: argparse.Namespace) -> None:
        """
        Send an interswarm message to the MAIL server.
        """
        try:
            response = await self.client.send_interswarm_message(
                args.body, args.targets, args.user_token
            )
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] sending interswarm message: {e}")

    async def _load_swarm_from_json(self, args: argparse.Namespace) -> None:
        """
        Load a swarm from a JSON document.
        """
        try:
            response = await self.client.load_swarm_from_json(args.swarm_json)
            self.client._console.print(json.dumps(response, indent=2))
        except Exception as e:
            self.client._console.print(f"[red bold]error[/red bold] loading swarm from JSON: {e}")

    def _print_preamble(self) -> None:
        """
        Print the preamble for the MAIL client.
        """
        self.client._console.print(f"MAIL CLIent v[cyan bold]{utils.get_version()}[/cyan bold]")
        self.client._console.print("Enter [cyan]`help`[/cyan] for help and [cyan]`exit`[/cyan] to quit")
        self.client._console.print("==========")

    def _repl_input_string(
        self,
        username: str,
        base_url: str,
    ) -> str:
        """
        Get the input string for the REPL.
        """
        base_url = base_url.removeprefix("http://")
        base_url = base_url.removeprefix("https://")
        return f"[cyan bold]mail[/cyan bold]::[green bold]{username}@{base_url}[/green bold]> "

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
                self.username = whoami["username"]
                self.base_url = self.client.base_url
            except Exception as e:
                self.client._console.print(f"[red bold]error[/red bold] logging into swarm: {e}")
                return
        else:
            self.username = "unknown"
            self.base_url = self.client.base_url

        self._print_preamble()

        while True:
            try:
                raw_command = self.client._console.input(self._repl_input_string(self.username, self.base_url))
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
                self.client._console.print(f"[red bold]error[/red bold] parsing command: {exc}")
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
