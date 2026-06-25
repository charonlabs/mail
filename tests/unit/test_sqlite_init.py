# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Coverage for ``init_sqlite_backend`` — the ``backend-init --type sqlite`` path.

Verifies it seeds the swarm + every user-agent, writes plaintext secrets whose
hash verifies, and is safely idempotent on re-run (no duplicates, secrets
preserved).
"""

from pathlib import Path

from mail_protocol.core.user_agents import MAILAdmin
from mail_server.auth import verify_password
from mail_server.backends.sqlite.api import SQLiteBackend
from mail_server.backends.sqlite.init import default_sqlite_path, init_sqlite_backend

_ADMIN = MAILAdmin(ua_type="admin", admin_id="ryan", host="localhost")


def test_default_sqlite_path_layout() -> None:
    path = default_sqlite_path("mydep")
    assert path.name == "mail.db"
    assert path.parent.name == "mydep"
    assert path.parent.parent.name == "deployments"


async def test_init_seeds_swarm_agents_and_secrets(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.db"
    await init_sqlite_backend(
        swarm="chorus",
        agents=["supervisor"],
        daemons=["dummy"],
        users=["alice"],
        admins=["ryan"],
        host="localhost",
        db_path=db_path,
    )

    assert db_path.exists()
    secrets_dir = tmp_path / ".secrets"
    addresses = {
        "supervisor@chorus@localhost",
        "daemon:dummy@localhost",
        "user:alice@localhost",
        "admin:ryan@localhost",
    }
    assert {p.name for p in secrets_dir.iterdir()} == addresses

    backend = SQLiteBackend(f"sqlite:///{db_path}")
    await backend.on_server_startup(host="localhost")
    try:
        assert (await backend.get_swarm("chorus")).agents == ["supervisor"]
        for address in addresses:
            ua = await backend.get_user_agent(address)
            secret = (secrets_dir / address).read_text(encoding="utf-8")
            # The plaintext written to disk verifies against the stored hash.
            assert verify_password(
                plain_password=secret, hashed_password=ua.hashed_password
            )
    finally:
        await backend.on_server_shutdown()


async def test_init_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.db"
    kwargs = dict(
        swarm="chorus",
        agents=["supervisor"],
        daemons=["dummy"],
        users=["alice"],
        admins=["ryan"],
        host="localhost",
        db_path=db_path,
    )
    await init_sqlite_backend(**kwargs)  # type: ignore[arg-type]
    secret_before = (tmp_path / ".secrets" / "user:alice@localhost").read_text()

    # Re-running must not duplicate rows or rotate the existing secret.
    await init_sqlite_backend(**kwargs)  # type: ignore[arg-type]
    secret_after = (tmp_path / ".secrets" / "user:alice@localhost").read_text()
    assert secret_before == secret_after

    backend = SQLiteBackend(f"sqlite:///{db_path}")
    await backend.on_server_startup(host="localhost")
    try:
        assert await backend.admin_get_users(_ADMIN) == ["alice"]
        assert await backend.admin_get_agents(_ADMIN) == ["supervisor@chorus"]
    finally:
        await backend.on_server_shutdown()
