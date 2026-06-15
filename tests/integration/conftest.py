# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import os
from pathlib import Path

# mail_server.server reads MAIL_HOST and mail_server.routers.auth reads
# MAIL_JWT_EXPIRE_MINUTES at import time. MAIL_HOST is forced (not
# setdefault) because every seeded address below assumes ``localhost``.
os.environ["MAIL_HOST"] = "localhost"
os.environ.setdefault("MAIL_JWT_EXPIRE_MINUTES", "15")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mail_protocol.core.swarms import MAILSwarm  # noqa: E402
from mail_protocol.core.user_agents import (  # noqa: E402
    MAILAdmin,
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgentInBackend,
)
from mail_server import server as mail_server_module  # noqa: E402
from mail_server.auth import get_password_hash  # noqa: E402
from mail_server.backends.memory.api import MemoryBackend  # noqa: E402

HOST = "localhost"
SWARM = "chorus"

ADMIN = f"admin:ryan@{HOST}"
USER = f"user:alice@{HOST}"
OTHER_USER = f"user:bob@{HOST}"
AGENT = f"sage@{SWARM}@{HOST}"
DAEMON = f"daemon:dummy@{HOST}"

PASSWORD = "correct-horse-battery-staple"

# Argon2 hashing is deliberately slow; hash the shared cast password once
# per session instead of once per seeded user-agent per test.
PASSWORD_HASH = get_password_hash(PASSWORD)


def _seed_cast(backend: MemoryBackend) -> None:
    """
    Seed the standard cast: one admin, two users, one agent, one daemon,
    and one swarm — all sharing PASSWORD. Mirrors what `backend-init`
    plus admin CRUD calls would provision.
    """

    cast = {
        ADMIN: MAILAdmin(ua_type="admin", admin_id="ryan", host=HOST),
        USER: MAILUser(ua_type="user", user_id="alice", host=HOST),
        OTHER_USER: MAILUser(ua_type="user", user_id="bob", host=HOST),
        AGENT: MAILAgent(ua_type="agent", name="sage", swarm=SWARM, host=HOST),
        DAEMON: MAILDaemon(ua_type="daemon", worker_name="dummy", host=HOST),
    }
    for address, user_agent in cast.items():
        backend.user_agents[address] = MAILUserAgentInBackend(
            user_agent=user_agent,
            hashed_password=PASSWORD_HASH,
        )
        backend.inboxes[address] = []
        backend.outboxes[address] = []
        backend.drafts[address] = []
        backend.trashes[address] = []

    backend.swarms[SWARM] = MAILSwarm(
        name=SWARM,
        description="integration test swarm",
        keywords=["testing"],
        agents=["sage"],
        metadata={},
    )


@pytest.fixture
def app_client(
    deployment_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """
    The real composed FastAPI app over ASGI with a fresh MemoryBackend,
    seeded with the standard cast. Auth is NOT monkeypatched — requests
    must carry real JWTs (see ``token_for`` / ``headers_for``).
    """

    monkeypatch.setattr(mail_server_module, "_backend", MemoryBackend())
    with TestClient(mail_server_module.app) as client:
        _seed_cast(client.app.state.backend)
        yield client


@pytest.fixture
def backend(app_client: TestClient) -> MemoryBackend:
    """The backend behind ``app_client`` (overrides the root fixture)."""

    return app_client.app.state.backend


@pytest.fixture
def token_for(app_client: TestClient):
    """Factory issuing a real JWT via ``POST /auth/token``."""

    def _token(address: str, password: str = PASSWORD) -> str:
        response = app_client.post(
            "/auth/token",
            data={"username": address, "password": password},
        )
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    return _token


@pytest.fixture
def headers_for(token_for):
    """Factory producing ``Authorization: Bearer <real JWT>`` headers."""

    def _headers(address: str, password: str = PASSWORD) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(address, password)}"}

    return _headers


@pytest.fixture
def deliver_message(app_client: TestClient, headers_for):
    """
    Drive the full send path through the API: compose a draft, send it,
    then clear the buffer and deliver as the daemon. Returns the
    message ID.
    """

    def _deliver(
        sender: str,
        recipients: list[str],
        subject: str = "Hello",
        body: str = "World",
    ) -> str:
        sender_headers = headers_for(sender)
        daemon_headers = headers_for(DAEMON)

        response = app_client.post(
            "/drafts",
            json={"subject": subject, "body": body},
            headers=sender_headers,
        )
        assert response.status_code == 200, response.text
        draft_id = response.json()["entry"]["draft"]["draft_id"]

        response = app_client.post(
            f"/drafts/{draft_id}/send",
            json={"recipients": recipients},
            headers=sender_headers,
        )
        assert response.status_code == 200, response.text
        message_id = response.json()["message"]["message_id"]

        response = app_client.post(
            "/daemon/message-buffer/clear",
            headers=daemon_headers,
        )
        assert response.status_code == 200, response.text
        assert message_id in response.json()["message_ids"]

        response = app_client.post(
            "/daemon/deliver/local",
            json={"message_ids": [message_id]},
            headers=daemon_headers,
        )
        assert response.status_code == 200, response.text

        return message_id

    return _deliver
