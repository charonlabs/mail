# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

"""Run the MAIL server in-process and exercise MAILClient requests."""

from __future__ import annotations

import asyncio
import datetime
import os
import sys
import uuid
from typing import Any

import uvicorn
from sse_starlette import EventSourceResponse, ServerSentEvent

from mail.client import MAILClient
from mail.core.message import MAILMessage


class DemoSwarmRegistry:
    """Non-persisted registry stub used by the demo server."""

    def __init__(
        self,
        local_swarm_name: str,
        base_url: str,
        persistence_file: str | None = None,
    ) -> None:
        self.local_swarm_name = local_swarm_name
        self.base_url = base_url
        self.persistence_file = persistence_file or "demo-registry.json"
        self._endpoints: dict[str, dict[str, Any]] = {}
        self.register_swarm(local_swarm_name, base_url, volatile=False)

    async def start_health_checks(self) -> None:
        return None

    async def stop_health_checks(self) -> None:
        return None

    def cleanup_volatile_endpoints(self) -> None:
        self._endpoints = {
            name: data
            for name, data in self._endpoints.items()
            if not data.get("volatile", False)
        }

    def register_swarm(
        self,
        swarm_name: str,
        base_url: str,
        auth_token: str | None = None,
        metadata: dict[str, Any] | None = None,
        volatile: bool = True,
    ) -> None:
        self._endpoints[swarm_name] = {
            "swarm_name": swarm_name,
            "base_url": base_url,
            "health_check_url": f"{base_url}/health",
            "auth_token_ref": auth_token,
            "last_seen": datetime.datetime.now(datetime.UTC),
            "is_active": True,
            "metadata": metadata,
            "volatile": volatile,
        }

    def get_swarm_endpoint(self, swarm_name: str) -> dict[str, Any] | None:
        return self._endpoints.get(swarm_name)

    def get_all_endpoints(self) -> dict[str, dict[str, Any]]:
        return self._endpoints.copy()


class DemoMAILSwarm:
    """
    Simplified MAIL swarm that echoes user messages.
    """

    def __init__(self, user_id: str, swarm_name: str) -> None:
        self.user_id = user_id
        self.swarm_name = swarm_name
        self.enable_interswarm = False
        self._stop = asyncio.Event()

    async def start_interswarm(self) -> None:
        return None

    async def run_continuous(self) -> None:
        try:
            await self._stop.wait()
        except asyncio.CancelledError:
            return None

    async def shutdown(self) -> None:
        self._stop.set()

    async def post_message(
        self,
        *,
        subject: str,
        body: str,
        entrypoint: str,
        show_events: bool,
    ) -> tuple[MAILMessage, list[ServerSentEvent]]:
        task_id = str(uuid.uuid4())
        response: MAILMessage = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "msg_type": "response",
            "message": {
                "task_id": task_id,
                "request_id": str(uuid.uuid4()),
                "sender": {"address_type": "agent", "address": entrypoint},
                "recipient": {
                    "address_type": "user",
                    "address": f"demo-user:{self.user_id}",
                },
                "subject": subject,
                "body": f"Demo response: {body}",
                "sender_swarm": self.swarm_name,
                "recipient_swarm": self.swarm_name,
                "routing_info": {},
            },
        }
        events = [ServerSentEvent(event="task_complete", data="demo complete")]
        return response, events if show_events else []

    async def post_message_stream(
        self,
        *,
        subject: str,
        body: str,
        entrypoint: str,
    ) -> EventSourceResponse:
        async def _event_source() -> Any:
            yield ServerSentEvent(event="message", data="processing")
            yield ServerSentEvent(event="task_complete", data=f"Demo response: {body}")

        return EventSourceResponse(_event_source())

    def get_pending_requests(self) -> dict[str, Any]:
        return {}

    async def handle_interswarm_response(self, _: MAILMessage) -> None:
        return None

    async def route_interswarm_message(self, message: MAILMessage) -> MAILMessage:
        return message

    def get_events_by_task_id(self, _: str) -> list[ServerSentEvent]:
        return [ServerSentEvent(event="task_complete", data="demo complete")]


class DemoSwarmTemplate:
    """
    Swarm template stub that vends DemoMAILSwarm instances.
    """

    def __init__(self, swarm_name: str) -> None:
        self.name = swarm_name
        self.entrypoint = "supervisor"
        self.enable_interswarm = False
        self.agents: list[Any] = []

    def instantiate(
        self,
        *,
        instance_params: dict[str, Any] | None = None,
        user_id: str,
        base_url: str,
        registry_file: str,
    ) -> DemoMAILSwarm:  # noqa: ARG002
        return DemoMAILSwarm(user_id, self.name)


async def patch_server() -> None:
    """
    Apply runtime patches so the real server uses demo stubs.
    """
    import mail.server as server
    import mail.utils as utils
    import mail.utils.auth as auth

    server.SwarmRegistry = DemoSwarmRegistry  # type: ignore[attr-defined]
    server.MAILSwarmTemplate.from_swarm_json_file = staticmethod(  # type: ignore[assignment, misc]
        lambda swarm_name, _=None: DemoSwarmTemplate(swarm_name)
    )
    server.user_mail_instances.clear() # type: ignore[attr-defined]
    server.user_mail_tasks.clear() # type: ignore[attr-defined]
    server.swarm_mail_instances.clear() # type: ignore[attr-defined]
    server.swarm_mail_tasks.clear() # type: ignore[attr-defined]
    server.swarm_registry = None # type: ignore[attr-defined]
    server.persistent_swarm = None # type: ignore[attr-defined]

    async def _fake_login(_: str) -> str:
        return "demo-token"

    async def _fake_token(_: str) -> dict[str, str]:
        return {"role": "user", "id": "demo"}

    auth.login = _fake_login  # type: ignore[assignment]
    auth.get_token_info = _fake_token  # type: ignore[assignment]
    utils.login = _fake_login  # type: ignore[assignment]
    utils.get_token_info = _fake_token  # type: ignore[assignment]


async def wait_for_server(host: str, port: int) -> None:
    """
    Poll the health endpoint until the server signals readiness.
    """
    import aiohttp

    url = f"http://{host}:{port}/health"
    for _ in range(50):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=1)
                ) as resp:
                    if resp.status == 200:
                        return
        except Exception:
            await asyncio.sleep(0.1)
            continue
        raise RuntimeError("server did not start in time")


async def main() -> None:
    base_host = "127.0.0.1"
    base_port = 8070
    base_url = f"http://{base_host}:{base_port}"
    os.environ["SWARM_NAME"] = "demo-swarm"
    os.environ["BASE_URL"] = base_url
    os.environ.setdefault("AUTH_ENDPOINT", "http://demo-auth.local/login")
    os.environ.setdefault("TOKEN_INFO_ENDPOINT", "http://demo-auth.local/token-info")

    await patch_server()
    import mail.server as server

    config = uvicorn.Config(
        server.app, host=base_host, port=base_port, log_level="error"
    )
    uvicorn_server = uvicorn.Server(config)
    server_future = asyncio.create_task(uvicorn_server.serve())
    while not uvicorn_server.started:
        await asyncio.sleep(0.05)

    await wait_for_server(base_host, base_port)

    try:
        async with MAILClient(base_url, api_key="demo-token") as client:
            root = await client.ping()
            status = await client.get_status()
            message = await client.post_message(
                "Ping from demo client", show_events=True
            )

            print("GET / ->", root)
            print("GET /status ->", status)
            print("POST /message ->", message)
    finally:
        uvicorn_server.should_exit = True
        await server_future


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
