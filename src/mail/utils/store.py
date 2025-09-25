# SPDX-License-Identifier: Apache-2.0
# Copyright (c) Jacob Hahn

import contextlib
import os

try:
    from langgraph.store.postgres.aio import (  # type: ignore
        AsyncPostgresStore,
        PostgresIndexConfig,
    )

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    # Fallback to in-memory store
    from langgraph.store.memory import InMemoryStore


@contextlib.asynccontextmanager
async def get_langmem_store():
    """Async context manager for memory store operations."""
    if POSTGRES_AVAILABLE:
        # Get and prepare connection string
        conn_string = os.getenv("DATABASE_URL", "none")
        if conn_string == "none":
            raise ValueError("DATABASE_URL is not set")

        # Replace asyncpg with regular postgres driver and add schema
        conn_string = conn_string.replace("postgresql+asyncpg://", "postgresql://")
        conn_string = conn_string + "?options=-csearch_path%3Dlangmem,public"

        index_config = PostgresIndexConfig(
            dims=1536,
            embed="openai:text-embedding-3-small",
        )

        async with AsyncPostgresStore.from_conn_string(
            conn_string, index=index_config
        ) as store:
            yield store
    else:
        # Fallback to in-memory store
        store = InMemoryStore()
        try:
            yield store
        finally:
            # InMemoryStore doesn't need explicit cleanup, but we keep the context manager pattern
            pass
