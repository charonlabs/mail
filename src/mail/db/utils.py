# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import asyncio
import logging
import os
from typing import Any, Literal

import asyncpg
import dotenv

from mail.db.types import AgentHistoriesDB

logger = logging.getLogger("mail.db")

# global connection pool
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """
    Get or create the global connection pool.
    """
    global _pool

    if _pool is None:
        dotenv.load_dotenv()
        database_url = os.getenv("DATABASE_URL")
        if database_url is None:
            raise ValueError("DATABASE_URL is not set")
        
        logger.info(f"creating new connection pool to {database_url}")
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=5,
            max_size=20,
            command_timeout=60,
            server_settings={
                "application_name": "mail-server"
            }
        )
        logger.info("connection pool created")
        
    return _pool


async def close_pool() -> None:
    """
    Close the global connection pool.
    """
    global _pool

    if _pool is not None:
        logger.info("closing connection pool")
        await _pool.close()
        _pool = None
        logger.info("connection pool closed")
    else:
        logger.info("connection pool already closed")


async def _db_execute(
    query: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Any:
    """
    Execute a database query and return the result, with retry logic for transient errors.
    """
    pool = await get_pool()

    for attempt in range(max_retries):
        try:
            async with pool.acquire() as connection:
                result = await connection.fetch(query)
                return result
        except asyncpg.ConnectionDoesNotExistError:
            # connection was closed, try to recreate pool
            if attempt < max_retries - 1:
                logger.warning(f"database connection lost, retrying... ({attempt + 1}/{max_retries})")
                global _pool
                _pool = None
                await asyncio.sleep(retry_delay)
                pool = await get_pool()
            else:
                logger.error(f"failed to reconnect to database after {max_retries} attempts")
                raise
        except asyncpg.ConnectionFailureError as e:
            if attempt < max_retries - 1:
                logger.warning(f"database connection failure (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"failed to reconnect to database after {max_retries} attempts: {e}")
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"database query failed (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"failed to execute query after {max_retries} attempts: {e}")
                raise

    raise RuntimeError(f"failed to execute query after {max_retries} attempts")


async def create_agent_history(
    swarm_name: str,
    caller_role: Literal["admin", "agent", "user"],
    caller_id: str,
    tool_format: Literal["completions", "responses"],
    task_id: str,
    agent_name: str,
    history: list[dict[str, Any]],
) -> None:
    """
    Create a new agent history record in the database.
    """
    import json

    pool = await get_pool()
    query = """
    INSERT INTO agent_histories (swarm_name, caller_role, caller_id, tool_format, task_id, agent_name, history)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    """

    async with pool.acquire() as connection:
        await connection.execute(
            query,
            swarm_name,
            caller_role,
            caller_id,
            tool_format,
            task_id,
            agent_name,
            json.dumps(history),
        )


async def create_agent_histories_table() -> Any:
    """
    Create the agent history table in the database.
    """
    query = """
    CREATE TABLE IF NOT EXISTS agent_histories (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        swarm_name TEXT NOT NULL,
        caller_role TEXT NOT NULL,
        caller_id TEXT NOT NULL,
        tool_format TEXT NOT NULL,
        task_id TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        history JSONB NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """
    result = await _db_execute(query)
    return result