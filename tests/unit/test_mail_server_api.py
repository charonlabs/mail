# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from mail_protocol.core.swarm import MAILSwarm
from mail_protocol.interswarm import MAILRemoteSwarm

import mail_server.auth as mail_server_auth
from mail_server import MAILServer
from mail_server.types import PersistedSwarmRegistry, SwarmRegistryEntry


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("MAIL_SERVER_JWT_SECRET", "test-secret")
    monkeypatch.setenv("MAIL_SERVER_JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("MAIL_SERVER_JWT_LIFETIME_MINUTES", "60")
    mail_server_auth.get_auth_settings.cache_clear()
    yield
    mail_server_auth.get_auth_settings.cache_clear()


def build_swarm(name: str = "local-swarm") -> MAILSwarm:
    return MAILSwarm(
        name=name,
        agents=["supervisor"],
        entrypoints=["supervisor"],
        keywords=["mail"],
        description="Test MAIL server",
        metadata={},
    )


def build_remote_swarm(name: str, base_url: str) -> MAILRemoteSwarm:
    return MAILRemoteSwarm(
        name=name,
        base_url=base_url,
        protocol_version="2.0",
        active=True,
        last_seen="2026-03-06T12:00:00+00:00",
        description="Remote swarm",
        keywords=["remote"],
        metadata={},
    )


def build_registry_entry(
    name: str,
    base_url: str,
    *,
    public: bool = True,
    volatile: bool = False,
) -> SwarmRegistryEntry:
    return SwarmRegistryEntry(
        swarm=build_remote_swarm(name=name, base_url=base_url),
        api_key_ref=f"{name.upper().replace('-', '_')}_API_KEY",
        public=public,
        volatile=volatile,
    )


def auth_headers(role: str, client_id: str) -> dict[str, str]:
    token = jwt.encode(
        {"role": role, "id": client_id},
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_lifecycle_hooks_and_registry_persistence(tmp_path, auth_env):
    registry_path = tmp_path / "registry.json"
    persisted_registry = PersistedSwarmRegistry(
        entries={
            "loaded": build_registry_entry(
                "loaded",
                "http://loaded.example",
                volatile=False,
            )
        }
    )
    registry_path.write_text(json.dumps(persisted_registry.model_dump(mode="json")))

    server = MAILServer(
        swarm=build_swarm(),
        registry_path=registry_path,
    )
    events: list[str] = []

    @server.on_startup
    def startup_a() -> None:
        events.append("startup_a")

    @server.on_startup
    async def startup_b(mail_server: MAILServer) -> None:
        events.append("startup_b")
        assert "loaded" in mail_server.registry
        mail_server.registry["persisted"] = build_registry_entry(
            "persisted",
            "http://persisted.example",
            volatile=False,
        )
        mail_server.registry["volatile"] = build_registry_entry(
            "volatile",
            "http://volatile.example",
            volatile=True,
        )

    @server.on_shutdown
    def shutdown_a() -> None:
        events.append("shutdown_a")

    @server.on_shutdown
    async def shutdown_b(mail_server: MAILServer) -> None:
        events.append("shutdown_b")
        assert "persisted" in mail_server.registry

    with TestClient(server.app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert "loaded" in server.registry

    assert events == ["startup_a", "startup_b", "shutdown_b", "shutdown_a"]

    saved_registry = PersistedSwarmRegistry.model_validate_json(registry_path.read_text())
    assert set(saved_registry.entries) == {"loaded", "persisted"}
    assert "volatile" not in saved_registry.entries

    reloaded_server = MAILServer(
        swarm=build_swarm(name="reloaded-swarm"),
        registry_path=registry_path,
    )
    with TestClient(reloaded_server.app):
        assert set(reloaded_server.registry) == {"loaded", "persisted"}


def test_registry_writes_and_message_handler(tmp_path, monkeypatch, auth_env):
    registry_path = tmp_path / "registry.json"
    server = MAILServer(
        swarm=build_swarm(),
        registry_path=registry_path,
    )

    @server.on_message
    async def handle_message(message):
        return message, {"handled": True}

    async def fake_fetch_remote_swarm(base_url: str) -> MAILRemoteSwarm:
        if base_url.endswith("/persisted"):
            return build_remote_swarm("persisted-remote", base_url)
        return build_remote_swarm("volatile-remote", base_url)

    monkeypatch.setattr(server, "_fetch_remote_swarm", fake_fetch_remote_swarm)
    monkeypatch.setenv("PERSISTED_REMOTE_API_KEY", "persisted-secret")
    monkeypatch.setenv("VOLATILE_REMOTE_API_KEY", "volatile-secret")

    with TestClient(server.app) as client:
        message_response = client.post(
            "/message",
            headers=auth_headers("user", "user-123"),
            json={
                "task_id": str(uuid.uuid4()),
                "msg_type": "direct",
                "subject": "Hello",
                "body": "Test body",
                "recipients": [{"addr_type": "agent", "address": "supervisor"}],
                "metadata": {},
            },
        )
        assert message_response.status_code == 200
        assert message_response.json()["metadata"] == {"handled": True}
        assert message_response.json()["message"]["sender"]["addr_type"] == "user"

        persisted_response = client.post(
            "/registry",
            headers=auth_headers("admin", "admin-123"),
            json={
                "base_url": "http://remote.example/persisted",
                "api_key_ref": "PERSISTED_REMOTE_API_KEY",
                "public": True,
                "volatile": False,
                "metadata": {},
            },
        )
        assert persisted_response.status_code == 200
        assert "persisted-remote" in server.registry

        volatile_response = client.post(
            "/registry",
            headers=auth_headers("admin", "admin-123"),
            json={
                "base_url": "http://remote.example/volatile",
                "api_key_ref": "VOLATILE_REMOTE_API_KEY",
                "public": True,
                "volatile": True,
                "metadata": {},
            },
        )
        assert volatile_response.status_code == 200
        assert "volatile-remote" in server.registry

        delete_forbidden_response = client.delete(
            "/registry/persisted-remote",
            headers=auth_headers("user", "user-123"),
        )
        assert delete_forbidden_response.status_code == 401
        assert "persisted-remote" in server.registry

        delete_response = client.delete(
            "/registry/persisted-remote",
            headers=auth_headers("admin", "admin-123"),
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "success"
        assert delete_response.json()["swarm"]["name"] == "persisted-remote"
        assert "persisted-remote" not in server.registry

        missing_delete_response = client.delete(
            "/registry/missing-remote",
            headers=auth_headers("admin", "admin-123"),
        )
        assert missing_delete_response.status_code == 404

    saved_registry = PersistedSwarmRegistry.model_validate_json(registry_path.read_text())
    assert set(saved_registry.entries) == set()
