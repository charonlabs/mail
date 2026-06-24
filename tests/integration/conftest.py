# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime
from pathlib import Path

# mail_server.server reads MAIL_HOST and mail_server.routers.auth reads
# MAIL_JWT_EXPIRE_MINUTES at import time. MAIL_HOST is forced (not
# setdefault) because every seeded address below assumes ``localhost``.
os.environ["MAIL_HOST"] = "localhost"
os.environ.setdefault("MAIL_JWT_EXPIRE_MINUTES", "15")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mail_protocol.core.lists import MAILListInBackend  # noqa: E402
from mail_protocol.core.messages import MAILMessage  # noqa: E402
from mail_protocol.core.swarms import MAILSwarm  # noqa: E402
from mail_protocol.core.trash import MAILTrashEntry  # noqa: E402
from mail_protocol.core.user_agents import (  # noqa: E402
    MAILAdmin,
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgentInBackend,
)
from mail_server import server as mail_server_module  # noqa: E402
from mail_server.auth import get_password_hash  # noqa: E402
from mail_server.backends.base import MAILServerBackend  # noqa: E402
from mail_server.backends.memory.api import MemoryBackend  # noqa: E402
from mail_server.backends.sqlite.api import SQLiteBackend  # noqa: E402
from mail_server.backends.sqlite.database import Database  # noqa: E402
from mail_server.backends.sqlite.repositories import (  # noqa: E402
    BOX_TRASH,
    MailStore,
)

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

# The integration suite runs against every backend in this list. Backend
# internals are never touched directly — seeding/assertions go through the
# public API or the backend-agnostic ``seed_*`` fixtures below — so each test
# exercises identical behavior on memory and sqlite.
BACKENDS = ["memory", "sqlite"]


def _cast() -> dict[str, MAILUserAgentInBackend]:
    """The standard cast (one admin, two users, one agent, one daemon)."""

    members = {
        ADMIN: MAILAdmin(ua_type="admin", admin_id="ryan", host=HOST),
        USER: MAILUser(ua_type="user", user_id="alice", host=HOST),
        OTHER_USER: MAILUser(ua_type="user", user_id="bob", host=HOST),
        AGENT: MAILAgent(ua_type="agent", name="sage", swarm=SWARM, host=HOST),
        DAEMON: MAILDaemon(ua_type="daemon", worker_name="dummy", host=HOST),
    }
    return {
        address: MAILUserAgentInBackend(
            user_agent=user_agent, hashed_password=PASSWORD_HASH
        )
        for address, user_agent in members.items()
    }


def _swarm() -> MAILSwarm:
    return MAILSwarm(
        name=SWARM,
        description="integration test swarm",
        keywords=["testing"],
        agents=["sage"],
        metadata={},
    )


def _seed_memory_cast(backend: MemoryBackend) -> None:
    for address, ua_in_be in _cast().items():
        backend.user_agents[address] = ua_in_be
        backend.inboxes[address] = []
        backend.outboxes[address] = []
        backend.drafts[address] = []
        backend.trashes[address] = []
    backend.swarms[SWARM] = _swarm()


def _run_sqlite_write(
    url: str,
    mutate: Callable[[MailStore], Awaitable[object]],
    *,
    create_schema: bool = False,
) -> None:
    """
    Apply a write to a file-backed sqlite db via a throwaway engine.

    Per-test seeding can't reuse the app's engine (it is bound to the
    TestClient's event loop), so we open a short-lived ``Database`` on the same
    file in a fresh loop. WAL makes the committed rows visible to the app, and
    seeding is sequential with the HTTP calls, so there is no write contention.
    """

    async def _run() -> None:
        db = Database(url)
        try:
            if create_schema:
                await db.create_schema()
            async with db.session() as session:
                await mutate(MailStore(session))
        finally:
            await db.dispose()

    asyncio.run(_run())


async def _seed_sqlite_cast(store: MailStore) -> None:
    for ua_in_be in _cast().values():
        await store.user_agents.add(ua_in_be)
    await store.swarms.add(_swarm())


@pytest.fixture(params=BACKENDS)
def backend_kind(request: pytest.FixtureRequest) -> str:
    """The backend under test for this parametrization (``memory``/``sqlite``)."""

    return request.param


@pytest.fixture
def app_client(
    backend_kind: str,
    deployment_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """
    The real composed FastAPI app over ASGI, seeded with the standard cast on
    the selected backend. Auth is NOT monkeypatched — requests must carry real
    JWTs (see ``token_for`` / ``headers_for``).
    """

    if backend_kind == "memory":
        monkeypatch.setattr(mail_server_module, "_backend", MemoryBackend())
        with TestClient(mail_server_module.app) as client:
            _seed_memory_cast(mail_server_module.app.state.backend)
            yield client
        return

    # sqlite: seed the cast (and create the schema) before the app starts, so
    # the rows are already committed when the lifespan runs.
    db_url = f"sqlite:///{tmp_path / 'mail.db'}"
    _run_sqlite_write(db_url, _seed_sqlite_cast, create_schema=True)
    monkeypatch.setattr(mail_server_module, "_backend", SQLiteBackend(url=db_url))
    with TestClient(mail_server_module.app) as client:
        yield client


@pytest.fixture
def backend(app_client: TestClient) -> MAILServerBackend:
    """The backend behind ``app_client`` (overrides the root fixture)."""

    backend: MAILServerBackend = mail_server_module.app.state.backend
    return backend


@pytest.fixture
def seed_trash(backend: MAILServerBackend) -> Callable[..., str]:
    """
    Backend-agnostic: place ``message`` directly in ``owner``'s trash with the
    given ``trashed_at`` (and register the message in the canonical store, which
    the ``sent_at`` sort resolves against). Returns the message id.

    Bypassing the API is deliberate — it lets a test pin ``trashed_at`` and the
    message's ``sent_at`` independently, which the natural inbox→trash flow
    (both stamped with the wall clock) cannot.
    """

    def _seed(owner: str, *, message: MAILMessage, trashed_at: datetime) -> str:
        entry = MAILTrashEntry(message=message, trashed_at=trashed_at)
        if isinstance(backend, MemoryBackend):
            backend.messages[message.message_id] = message
            backend.trash_entries[message.message_id] = entry
            backend.trashes.setdefault(owner, []).append(message.message_id)
        else:
            assert isinstance(backend, SQLiteBackend)

            async def mutate(store: MailStore) -> None:
                await store.messages.add(message)
                await store.boxes.upsert_trash_entry(entry)
                await store.boxes.add_membership(
                    owner, BOX_TRASH, message.message_id, trashed_at
                )

            _run_sqlite_write(backend._db.url, mutate)
        return message.message_id

    return _seed


@pytest.fixture
def seed_list(backend: MAILServerBackend) -> Callable[[MAILListInBackend], str]:
    """Backend-agnostic: persist a prebuilt list. Returns its address."""

    def _seed(record: MAILListInBackend) -> str:
        if isinstance(backend, MemoryBackend):
            backend.lists[record.get_address()] = record
        else:
            assert isinstance(backend, SQLiteBackend)

            async def mutate(store: MailStore) -> None:
                await store.lists.add(record)

            _run_sqlite_write(backend._db.url, mutate)
        return record.get_address()

    return _seed


@pytest.fixture
def list_members(
    app_client: TestClient, headers_for: Callable[..., dict[str, str]]
) -> Callable[..., list[str]]:
    """Read a list's members through the public API (backend-agnostic)."""

    def _members(address: str, viewer: str = USER) -> list[str]:
        response = app_client.get(f"/lists/{address}", headers=headers_for(viewer))
        assert response.status_code == 200, response.text
        return response.json()["mail_list"]["members"]

    return _members


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
