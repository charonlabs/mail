# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Conformance tests for the refresh-token backend protocol methods.

Each test runs against **both** the memory and sqlite backends via the
``rt_backend`` fixture, so the two implementations are held to identical
behavior (create / get / rotate / revoke-family / revoke-for-owner / purge).
Unlike the rest of the integration suite these exercise the backend protocol
directly rather than the FastAPI app — the HTTP-level refresh flow is covered in
the auth router tests.
"""

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mail_protocol.core.user_agents import MAILUser, MAILUserAgentInBackend
from mail_server.auth import get_password_hash
from mail_server.backends.base import MAILServerBackend
from mail_server.backends.memory.api import MemoryBackend
from mail_server.backends.sqlite.api import SQLiteBackend
from mail_server.backends.sqlite.repositories import MailStore

HOST = "localhost"
OWNER = f"user:alice@{HOST}"
OTHER = f"user:bob@{HOST}"

# Argon2 is deliberately slow; hash the throwaway password once.
_PWHASH = get_password_hash("pw")


def _user(user_id: str) -> MAILUserAgentInBackend:
    return MAILUserAgentInBackend(
        user_agent=MAILUser(ua_type="user", user_id=user_id, host=HOST),
        hashed_password=_PWHASH,
    )


def _h(label: str) -> str:
    """A deterministic, validly-shaped (64 hex) stand-in token hash."""

    return hashlib.sha256(label.encode()).hexdigest()


def _exp(*, days: int = 30) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


@pytest.fixture(params=["memory", "sqlite"])
async def rt_backend(
    request: pytest.FixtureRequest,
    deployment_dir: Path,
    tmp_path: Path,
) -> AsyncIterator[MAILServerBackend]:
    """A started backend seeded with two users (FK owners for refresh tokens)."""

    if request.param == "memory":
        backend: MAILServerBackend = MemoryBackend()
        await backend.on_server_startup(host=HOST)
        backend.user_agents[OWNER] = _user("alice")  # type: ignore[attr-defined]
        backend.user_agents[OTHER] = _user("bob")  # type: ignore[attr-defined]
        try:
            yield backend
        finally:
            await backend.on_server_shutdown()
        return

    db_url = f"sqlite:///{tmp_path / 'mail.db'}"
    sqlite_backend = SQLiteBackend(url=db_url)
    await sqlite_backend.on_server_startup(host=HOST)
    async with sqlite_backend._db.session() as session:
        store = MailStore(session)
        await store.user_agents.add(_user("alice"))
        await store.user_agents.add(_user("bob"))
    try:
        yield sqlite_backend
    finally:
        await sqlite_backend.on_server_shutdown()


async def test_create_and_get(rt_backend: MAILServerBackend) -> None:
    exp = _exp()
    await rt_backend.create_refresh_token(OWNER, _h("t1"), "fam1", exp)

    rec = await rt_backend.get_refresh_token(_h("t1"))
    assert rec is not None
    assert rec.token_hash == _h("t1")
    assert rec.owner_address == OWNER
    assert rec.family_id == "fam1"
    assert rec.revoked is False
    assert rec.rotated_at is None
    assert abs((rec.expires_at - exp).total_seconds()) < 1
    assert rec.issued_at <= datetime.now(UTC)


async def test_get_missing_returns_none(rt_backend: MAILServerBackend) -> None:
    assert await rt_backend.get_refresh_token(_h("nope")) is None


async def test_rotate_revokes_old_and_carries_expiry_forward(
    rt_backend: MAILServerBackend,
) -> None:
    exp = _exp()
    await rt_backend.create_refresh_token(OWNER, _h("old"), "fam", exp)

    await rt_backend.rotate_refresh_token(_h("old"), _h("new"))

    old = await rt_backend.get_refresh_token(_h("old"))
    new = await rt_backend.get_refresh_token(_h("new"))
    assert old is not None and new is not None
    # old half: revoked + rotated
    assert old.revoked is True
    assert old.rotated_at is not None
    # new half: live, same family, absolute cap unchanged
    assert new.revoked is False
    assert new.rotated_at is None
    assert new.family_id == "fam"
    assert new.owner_address == OWNER
    assert abs((new.expires_at - old.expires_at).total_seconds()) < 1


async def test_rotate_missing_raises(rt_backend: MAILServerBackend) -> None:
    with pytest.raises(ValueError):
        await rt_backend.rotate_refresh_token(_h("ghost"), _h("x"))


async def test_revoke_family_only_targets_that_family(
    rt_backend: MAILServerBackend,
) -> None:
    await rt_backend.create_refresh_token(OWNER, _h("a1"), "A", _exp())
    await rt_backend.create_refresh_token(OWNER, _h("a2"), "A", _exp())
    await rt_backend.create_refresh_token(OWNER, _h("b1"), "B", _exp())

    await rt_backend.revoke_refresh_family("A")

    a1 = await rt_backend.get_refresh_token(_h("a1"))
    a2 = await rt_backend.get_refresh_token(_h("a2"))
    b1 = await rt_backend.get_refresh_token(_h("b1"))
    assert a1 is not None and a1.revoked is True
    assert a2 is not None and a2.revoked is True
    assert b1 is not None and b1.revoked is False


async def test_revoke_all_for_owner_spares_other_owners(
    rt_backend: MAILServerBackend,
) -> None:
    await rt_backend.create_refresh_token(OWNER, _h("o1"), "X", _exp())
    await rt_backend.create_refresh_token(OTHER, _h("p1"), "Y", _exp())

    await rt_backend.revoke_all_refresh_tokens(OWNER)

    o1 = await rt_backend.get_refresh_token(_h("o1"))
    p1 = await rt_backend.get_refresh_token(_h("p1"))
    assert o1 is not None and o1.revoked is True
    assert p1 is not None and p1.revoked is False


async def test_purge_expired_removes_only_expired(
    rt_backend: MAILServerBackend,
) -> None:
    await rt_backend.create_refresh_token(
        OWNER, _h("dead"), "fam", datetime.now(UTC) - timedelta(seconds=1)
    )
    await rt_backend.create_refresh_token(OWNER, _h("live"), "fam", _exp())

    removed = await rt_backend.purge_expired_refresh_tokens()

    assert removed == 1
    assert await rt_backend.get_refresh_token(_h("dead")) is None
    assert await rt_backend.get_refresh_token(_h("live")) is not None


async def test_sqlite_user_delete_cascades_refresh_tokens(
    rt_backend: MAILServerBackend,
) -> None:
    if not isinstance(rt_backend, SQLiteBackend):
        pytest.skip("FK cascade-on-delete is a sqlite-specific guarantee")

    await rt_backend.create_refresh_token(OWNER, _h("c1"), "fam", _exp())
    async with rt_backend._db.session() as session:
        await MailStore(session).user_agents.delete(OWNER)

    assert await rt_backend.get_refresh_token(_h("c1")) is None
