# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Database plumbing for the MAIL SQLite backend.

``Database`` owns the async engine, the session factory, and the SQLite
pragmas. It mirrors the SQLAlchemy async stack used in chorus' ``db`` package:
``create_async_engine`` over ``sqlite+aiosqlite``, an ``async_sessionmaker``
with ``expire_on_commit=False``, WAL + ``foreign_keys=ON`` + ``busy_timeout``
configured via a ``connect`` event listener, and a ``session()`` context
manager that commits on success and rolls back on error.

All backend mutations are expected to run inside a single ``session()`` block so
that multi-step operations (e.g. ``send_draft``: insert message + outbox entry +
membership + buffer row) commit atomically. Keep session scopes short and never
hold a transaction open across non-DB ``await``s — in particular, webhook POSTs
must fire *after* the delivery transaction commits, never inside it.

See ``src/mail/server/docs/reference/backends.md`` for the backend overview.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from sqlalchemy import event
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mail_server.backends.sqlite.schema import Base

# Milliseconds SQLite waits on a held write lock before raising
# ``database is locked``. WAL lets readers proceed without blocking the writer,
# but writers still serialize; a non-zero busy timeout turns brief contention
# into a retry instead of an immediate error.
_BUSY_TIMEOUT_MS = 5000


class _Cursor(Protocol):
    def execute(self, statement: str) -> object: ...

    def close(self) -> None: ...


class _SQLiteConnection(Protocol):
    def cursor(self) -> _Cursor: ...


class Database:
    """Async engine + session factory for the SQLite backend."""

    def __init__(self, url: str):
        self.url = normalize_database_url(url)
        _ensure_sqlite_parent(self.url)
        self.engine = create_async_engine(self.url)
        _configure_sqlite(self.engine)
        self._sessions = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )

    async def create_schema(self) -> None:
        """Create every table/index, then run additive forward-compat guards."""

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(_ensure_schema_columns)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session that commits on success and rolls back on error."""

        async with self._sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        """Dispose the engine and its connection pool (server shutdown)."""

        await self.engine.dispose()


def normalize_database_url(url: str) -> str:
    """
    Map a plain driver URL onto its async driver.

    ``sqlite://`` → ``sqlite+aiosqlite://``. The ``postgresql://`` →
    ``postgresql+psycopg://`` rewrite is kept as the seam for a future Postgres
    backend (out of scope here) so the same repositories can target it later.
    """

    if url.startswith("sqlite://") and not url.startswith("sqlite+"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _ensure_schema_columns(connection: Connection) -> None:
    """
    Additive, ``create_all``-friendly schema guard.

    This is the forward-compatibility hook mirroring chorus' approach: when a
    queryable column is added to a ``*Row`` table in a later release, add an
    idempotent ``ALTER TABLE ... ADD COLUMN`` here so existing databases pick it
    up without a migration framework. There are no such additions yet, so this
    is currently a no-op.
    """

    del connection  # no additive columns yet; hook retained for forward-compat


def _ensure_sqlite_parent(url: str) -> None:
    """Create the parent directory for a file-backed SQLite database."""

    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return
    if parsed.database is None or parsed.database == ":memory:":
        return
    Path(parsed.database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite(engine: AsyncEngine) -> None:
    """Apply WAL, foreign-key enforcement, and a busy timeout per connection."""

    if not engine.url.drivername.startswith("sqlite"):
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(
        dbapi_connection: _SQLiteConnection,
        _connection_record: object,
    ) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        cursor.close()
