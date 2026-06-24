# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
One-time initialization for the SQLite backend, used by ``backend-init``.

Creates the deployment's database file + schema and seeds the same initial
state ``init_memory_backend`` writes — one swarm plus the requested agents /
daemons / users / admins, each with a generated password (hashed via
``PasswordHash``) and its plaintext written to the existing
``<deployment>/.secrets/<address>`` files so the rest of the tooling is
unchanged. No empty box files are needed: ``mailbox_items`` membership is
created lazily on first delivery.

Re-running against an existing deployment is safe — the swarm and any
user-agents that already exist are left untouched (their stored password hash
and secret file are preserved) rather than duplicated.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgentInBackend,
)
from pwdlib import PasswordHash

from mail_server.backends.sqlite.database import Database
from mail_server.backends.sqlite.repositories import MailStore

# The concrete user-agent variants ``backend-init`` seeds (the members of the
# ``MAILUserAgent.user_agent`` discriminated union).
type _UserAgentVariant = MAILAgent | MAILUser | MAILAdmin | MAILDaemon


def default_sqlite_path(deployment: str = "default") -> Path:
    """Default DB file for a deployment: ``~/.mail-swarms/.../<dep>/mail.db``."""

    return (
        Path.home()
        .joinpath(".mail-swarms", "deployments", deployment, "mail.db")
    )


async def _seed_user_agent(
    store: MailStore,
    password_hash: PasswordHash,
    secrets_path: Path,
    user_agent: _UserAgentVariant,
    label: str,
) -> None:
    """Insert one user-agent (if absent) and write its plaintext secret."""

    address = user_agent.get_address()
    if await store.user_agents.exists(address):
        print(f"{label} already exists, skipping: {address}")
        return

    password = secrets.token_urlsafe(32)
    await store.user_agents.add(
        MAILUserAgentInBackend(
            user_agent=user_agent,
            hashed_password=password_hash.hash(password),
        )
    )
    secrets_path.joinpath(address).write_text(password, encoding="utf-8")
    print(f"wrote new {label}: {address} (secret in {secrets_path})")


async def init_sqlite_backend(
    deployment: str = "default",
    swarm: str = "default",
    swarm_description: str = "A MAIL swarm",
    swarm_keywords: list[str] = [],
    agents: list[str] = ["supervisor"],
    daemons: list[str] = ["dummy"],
    users: list[str] = ["dummy"],
    admins: list[str] = ["dummy"],
    host: str = "example.com",
    db_path: Path | None = None,
) -> None:
    """Initialize a fresh SQLite backend for ``mail-server``."""

    db_path = db_path or default_sqlite_path(deployment)
    deployment_path = db_path.parent
    secrets_path = deployment_path.joinpath(".secrets")
    secrets_path.mkdir(parents=True, exist_ok=True)
    print(f"ensured deployment path: {deployment_path}")
    print(f"ensured secrets path: {secrets_path}")

    # ``Database`` creates the db file's parent dir and applies the schema.
    db = Database(f"sqlite:///{db_path}")
    await db.create_schema()
    print(f"ensured sqlite database + schema: {db_path}")

    password_hash = PasswordHash.recommended()
    try:
        async with db.session() as session:
            store = MailStore(session)

            if await store.swarms.get(swarm) is None:
                await store.swarms.add(
                    MAILSwarm(
                        name=swarm,
                        description=swarm_description,
                        keywords=swarm_keywords,
                        agents=agents,
                        metadata={},
                    )
                )
                print(f"wrote swarm: {swarm}")
            else:
                print(f"swarm already exists, skipping: {swarm}")

            for agent_name in agents:
                await _seed_user_agent(
                    store,
                    password_hash,
                    secrets_path,
                    MAILAgent(
                        ua_type="agent", name=agent_name, swarm=swarm, host=host
                    ),
                    "agent",
                )
            for daemon_name in daemons:
                await _seed_user_agent(
                    store,
                    password_hash,
                    secrets_path,
                    MAILDaemon(ua_type="daemon", worker_name=daemon_name, host=host),
                    "daemon",
                )
            for user_name in users:
                await _seed_user_agent(
                    store,
                    password_hash,
                    secrets_path,
                    MAILUser(ua_type="user", user_id=user_name, host=host),
                    "user",
                )
            for admin_name in admins:
                await _seed_user_agent(
                    store,
                    password_hash,
                    secrets_path,
                    MAILAdmin(ua_type="admin", admin_id=admin_name, host=host),
                    "admin",
                )
    finally:
        await db.dispose()

    print(f"sqlite backend initialization complete: {db_path}")
