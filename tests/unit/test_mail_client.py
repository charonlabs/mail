# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

import contextlib
import datetime
from collections import defaultdict
from typing import Any

import pytest
from aiohttp import web

from mail.client import MAILClient
from mail.config import ClientConfig

EXAMPLE_MAIL_MESSAGE: dict[str, Any] = {
    "id": "msg-001",
    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    "msg_type": "response",
    "message": {
        "task_id": "task-001",
        "request_id": "req-001",
        "sender": {"address_type": "agent", "address": "supervisor"},
        "recipient": {"address_type": "user", "address": "demo-user"},
        "subject": "Demo",
        "body": "Response body",
        "sender_swarm": "demo",
        "recipient_swarm": "demo",
        "routing_info": {},
    },
}

EXAMPLE_INTERSWARM_MESSAGE: dict[str, Any] = {
    "message_id": "im-001",
    "source_swarm": "demo",
    "target_swarm": "remote",
    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    "payload": EXAMPLE_MAIL_MESSAGE["message"],
    "msg_type": "response",
    "auth_token": "remote-token",
    "task_owner": "user:demo-user@demo",
    "task_contributors": ["agent:supervisor@demo"],
    "metadata": {},
}


@contextlib.asynccontextmanager
async def run_app(app: web.Application) -> Any:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_mail_client_rest_endpoints() -> None:
    captured: dict[str, list[Any]] = defaultdict(list)

    def assert_auth(request: web.Request) -> None:
        assert request.headers.get("Authorization") == "Bearer demo-token"

    async def handle_root(request: web.Request) -> web.Response:
        assert_auth(request)
        return web.json_response({"name": "mail", "status": "ok", "version": "1.3"})

    async def handle_status(request: web.Request) -> web.Response:
        assert_auth(request)
        return web.json_response(
            {
                "swarm": {"name": "demo", "status": "ready"},
                "active_users": 1,
                "user_mail_ready": True,
                "user_task_running": False,
            }
        )

    async def handle_message(request: web.Request) -> web.Response:
        assert_auth(request)
        payload = await request.json()
        captured["messages"].append(payload)
        return web.json_response({"response": "Demo reply"})

    async def handle_health(request: web.Request) -> web.Response:
        assert_auth(request)
        return web.json_response(
            {"status": "healthy", "swarm_name": "demo", "timestamp": "now"}
        )

    async def handle_swarms(request: web.Request) -> web.Response:
        assert_auth(request)
        return web.json_response({"swarms": []})

    async def handle_register_swarm(request: web.Request) -> web.Response:
        assert_auth(request)
        payload = await request.json()
        captured["registrations"].append(payload)
        return web.json_response(
            {"status": "registered", "swarm_name": payload["name"]}
        )

    async def handle_dump(request: web.Request) -> web.Response:
        assert_auth(request)
        return web.json_response({"status": "dumped", "swarm_name": "demo"})

    async def handle_interswarm_message(request: web.Request) -> web.Response:
        assert_auth(request)
        payload = await request.json()
        if "payload" in payload:
            captured["interswarm_wrapped"].append(payload)
            return web.json_response(EXAMPLE_MAIL_MESSAGE)
        captured["interswarm_send"].append(payload)
        return web.json_response({"response": EXAMPLE_MAIL_MESSAGE, "events": []})

    async def handle_interswarm_response(request: web.Request) -> web.Response:
        assert_auth(request)
        payload = await request.json()
        captured["interswarm_response"].append(payload)
        return web.json_response({"status": "success", "task_id": "task-001"})

    async def handle_swarm_load(request: web.Request) -> web.Response:
        assert_auth(request)
        payload = await request.json()
        captured["swarm_load"].append(payload)
        return web.json_response({"status": "success", "swarm_name": "demo"})

    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/status", handle_status)
    app.router.add_post("/message", handle_message)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/swarms", handle_swarms)
    app.router.add_post("/swarms", handle_register_swarm)
    app.router.add_get("/swarms/dump", handle_dump)
    app.router.add_post("/interswarm/response", handle_interswarm_response)
    app.router.add_post("/interswarm/message", handle_interswarm_message)
    app.router.add_post("/swarms/load", handle_swarm_load)

    async with run_app(app) as base_url:
        async with MAILClient(
            base_url, api_key="demo-token", config=ClientConfig()
        ) as client:
            root = await client.ping()
            status = await client.get_status()
            await client.post_message("hello world")
            await client.post_message(
                "needs events", entrypoint="other", show_events=True
            )
            health = await client.get_health()
            swarms = await client.get_swarms()
            await client.register_swarm(
                "test",
                "http://example.com",
                volatile=False,
                metadata={"label": "alpha"},
            )
            dump = await client.dump_swarm()
            await client.post_interswarm_message(EXAMPLE_INTERSWARM_MESSAGE)  # type: ignore[arg-type]
            await client.post_interswarm_response(EXAMPLE_MAIL_MESSAGE)  # type: ignore[arg-type]
            await client.send_interswarm_message(
                "hello", targets=["agent@remote"], user_token="demo-user"
            )
            load = await client.load_swarm_from_json("{}")

        assert root["name"] == "mail"
        assert status["swarm"]["status"] == "ready"
        assert health["status"] == "healthy"
        assert swarms["swarms"] == []
        assert dump["status"] == "dumped"
        assert load["status"] == "success"

    assert captured["messages"][0] == {
        "subject": "New Message",
        "body": "hello world",
        "msg_type": "request",
        "entrypoint": None,
        "show_events": False,
        "task_id": None,
        "resume_from": None,
        "kwargs": {},
    }
    assert captured["messages"][1]["body"] == "needs events"
    assert captured["messages"][1]["subject"] == "New Message"
    assert captured["messages"][1]["msg_type"] == "request"
    assert captured["messages"][1]["show_events"] is True
    assert captured["messages"][1]["entrypoint"] == "other"
    assert captured["messages"][1]["task_id"] is None
    assert captured["messages"][1]["resume_from"] is None
    assert captured["messages"][1]["kwargs"] == {}
    assert captured["registrations"][0]["volatile"] is False
    assert captured["registrations"][0]["metadata"] == {"label": "alpha"}
    assert captured["interswarm_wrapped"][0] == EXAMPLE_INTERSWARM_MESSAGE
    assert captured["interswarm_response"][0] == EXAMPLE_MAIL_MESSAGE
    assert captured["interswarm_send"][0] == {
        "body": "hello",
        "targets": ["agent@remote"],
        "user_token": "demo-user",
    }
    assert captured["swarm_load"][0]["json"] == "{}"


@pytest.mark.asyncio
async def test_mail_client_post_message_stream() -> None:
    stream_received: list[str] = []

    async def handle_stream(request: web.Request) -> web.StreamResponse:
        assert request.headers.get("Accept") == "text/event-stream"
        payload = await request.json()
        assert payload == {
            "subject": "New Message",
            "body": "eventful",
            "msg_type": "request",
            "entrypoint": None,
            "stream": True,
            "task_id": None,
            "resume_from": None,
            "kwargs": {},
        }
        resp = web.StreamResponse(
            status=200, headers={"Content-Type": "text/event-stream"}
        )
        await resp.prepare(request)
        await resp.write(b"event: ping\r\n\r\n")
        await resp.write(b"data: chunk-1\r\n\r\n")
        await resp.write(b"event: task_complete\r\n")
        await resp.write(b"data: final\r\n\r\n")
        await resp.write_eof()
        return resp

    app = web.Application()
    app.router.add_post("/message", handle_stream)

    async with run_app(app) as base_url:
        async with MAILClient(
            base_url, api_key="demo-token", config=ClientConfig()
        ) as client:
            stream_iterator = await client.post_message_stream("eventful")
            async for event in stream_iterator:
                stream_received.append(f"{event.event}:{event.data}")

    assert stream_received == ["ping:None", "message:chunk-1", "task_complete:final"]
