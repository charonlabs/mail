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
            server_settings={"application_name": "mail-server"},
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
                logger.warning(
                    f"database connection lost, retrying... ({attempt + 1}/{max_retries})"
                )
                global _pool
                _pool = None
                await asyncio.sleep(retry_delay)
                pool = await get_pool()
            else:
                logger.error(
                    f"failed to reconnect to database after {max_retries} attempts"
                )
                raise
        except asyncpg.ConnectionFailureError as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"database connection failure (attempt {attempt + 1}/{max_retries}): {e}"
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error(
                    f"failed to reconnect to database after {max_retries} attempts: {e}"
                )
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"database query failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error(
                    f"failed to execute query after {max_retries} attempts: {e}"
                )
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


async def load_agent_histories(
    swarm_name: str,
    caller_role: Literal["admin", "agent", "user"],
    caller_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """
    Load all agent histories for a given swarm, caller role, and caller ID.
    Returns a dictionary keyed by "{task_id}::{agent_name}" containing the history lists.
    """
    import json

    pool = await get_pool()
    query = """
    SELECT task_id, agent_name, history
    FROM agent_histories
    WHERE swarm_name = $1 AND caller_role = $2 AND caller_id = $3
    ORDER BY created_at ASC
    """

    histories: dict[str, list[dict[str, Any]]] = {}

    async with pool.acquire() as connection:
        rows = await connection.fetch(query, swarm_name, caller_role, caller_id)
        for row in rows:
            task_id = row["task_id"]
            agent_name = row["agent_name"]
            history_data = row["history"]

            # Parse JSON if it's a string, otherwise use as-is (asyncpg may auto-parse JSONB)
            if isinstance(history_data, str):
                history_list = json.loads(history_data)
            else:
                history_list = history_data

            key = f"{task_id}::{agent_name}"
            # If multiple records exist for the same key, extend the history
            if key in histories:
                histories[key].extend(history_list)
            else:
                histories[key] = history_list

    logger.info(
        f"loaded {len(histories)} agent history entries for {caller_role}:{caller_id}@{swarm_name}"
    )
    return histories


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


# =============================================================================
# Task Persistence Functions
# =============================================================================


async def create_task(
    task_id: str,
    swarm_name: str,
    caller_role: Literal["admin", "agent", "user"],
    caller_id: str,
    task_owner: str,
    task_contributors: list[str],
    remote_swarms: list[str],
    start_time: str,
    is_running: bool = True,
    completed: bool = False,
    title: str | None = None,
) -> None:
    """
    Create a new task record in the database.
    Uses INSERT ON CONFLICT to handle duplicate task_ids gracefully.
    """
    import datetime
    import json

    pool = await get_pool()
    query = """
    INSERT INTO tasks (task_id, swarm_name, caller_role, caller_id, task_owner,
                       task_contributors, remote_swarms, start_time, is_running, completed, title)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    ON CONFLICT (task_id, swarm_name, caller_role, caller_id) DO NOTHING
    """

    # Convert ISO string to datetime if needed
    if isinstance(start_time, str):
        start_time_dt = datetime.datetime.fromisoformat(start_time)
    else:
        start_time_dt = start_time

    async with pool.acquire() as connection:
        await connection.execute(
            query,
            task_id,
            swarm_name,
            caller_role,
            caller_id,
            task_owner,
            json.dumps(task_contributors),
            json.dumps(remote_swarms),
            start_time_dt,
            is_running,
            completed,
            title,
        )


async def update_task(
    task_id: str,
    swarm_name: str,
    caller_role: Literal["admin", "agent", "user"],
    caller_id: str,
    is_running: bool | None = None,
    completed: bool | None = None,
    task_contributors: list[str] | None = None,
    remote_swarms: list[str] | None = None,
    title: str | None = None,
) -> None:
    """
    Update an existing task record in the database.
    Only updates fields that are provided (not None).
    """
    import json

    pool = await get_pool()

    # Build dynamic update query
    updates = []
    params = []
    param_idx = 1

    if is_running is not None:
        updates.append(f"is_running = ${param_idx}")
        params.append(is_running)
        param_idx += 1

    if completed is not None:
        updates.append(f"completed = ${param_idx}")
        params.append(completed)
        param_idx += 1

    if task_contributors is not None:
        updates.append(f"task_contributors = ${param_idx}")
        params.append(json.dumps(task_contributors))  # type: ignore
        param_idx += 1

    if remote_swarms is not None:
        updates.append(f"remote_swarms = ${param_idx}")
        params.append(json.dumps(remote_swarms))  # type: ignore
        param_idx += 1

    if title is not None:
        updates.append(f"title = ${param_idx}")
        params.append(title) # type: ignore
        param_idx += 1

    if not updates:
        return  # Nothing to update

    updates.append(f"updated_at = NOW()")

    query = f"""
    UPDATE tasks
    SET {", ".join(updates)}
    WHERE task_id = ${param_idx} AND swarm_name = ${param_idx + 1}
          AND caller_role = ${param_idx + 2} AND caller_id = ${param_idx + 3}
    """
    params.extend([task_id, swarm_name, caller_role, caller_id])  # type: ignore

    async with pool.acquire() as connection:
        await connection.execute(query, *params)


async def load_tasks(
    swarm_name: str,
    caller_role: Literal["admin", "agent", "user"],
    caller_id: str,
) -> list[dict[str, Any]]:
    """
    Load all tasks for a given swarm, caller role, and caller ID.
    Returns a list of task records.
    """
    import json

    pool = await get_pool()
    query = """
    SELECT task_id, task_owner, task_contributors, remote_swarms,
           is_running, completed, start_time, title
    FROM tasks
    WHERE swarm_name = $1 AND caller_role = $2 AND caller_id = $3
    ORDER BY start_time ASC
    """

    tasks = []
    async with pool.acquire() as connection:
        rows = await connection.fetch(query, swarm_name, caller_role, caller_id)
        for row in rows:
            task_contributors = row["task_contributors"]
            remote_swarms = row["remote_swarms"]

            # Parse JSON if needed
            if isinstance(task_contributors, str):
                task_contributors = json.loads(task_contributors)
            if isinstance(remote_swarms, str):
                remote_swarms = json.loads(remote_swarms)

            tasks.append({
                "task_id": row["task_id"],
                "task_owner": row["task_owner"],
                "task_contributors": task_contributors,
                "remote_swarms": remote_swarms,
                "is_running": row["is_running"],
                "completed": row["completed"],
                "start_time": row["start_time"].isoformat() if row["start_time"] else None,
                "title": row["title"],
            })

    logger.info(
        f"loaded {len(tasks)} tasks for {caller_role}:{caller_id}@{swarm_name}"
    )
    return tasks


async def create_task_event(
    task_id: str,
    swarm_name: str,
    caller_role: Literal["admin", "agent", "user"],
    caller_id: str,
    event_type: str | None,
    event_data: str | None,
    event_id: str | None,
) -> None:
    """
    Create a new task event record in the database.
    """
    pool = await get_pool()
    query = """
    INSERT INTO task_events (task_id, swarm_name, caller_role, caller_id,
                             event_type, event_data, event_id)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    """

    async with pool.acquire() as connection:
        await connection.execute(
            query,
            task_id,
            swarm_name,
            caller_role,
            caller_id,
            event_type,
            event_data,
            event_id,
        )


async def load_task_events(
    task_id: str,
    swarm_name: str,
    caller_role: Literal["admin", "agent", "user"],
    caller_id: str,
) -> list[dict[str, Any]]:
    """
    Load all events for a specific task.
    Returns a list of event records in chronological order.
    """
    pool = await get_pool()
    query = """
    SELECT event_type, event_data, event_id
    FROM task_events
    WHERE task_id = $1 AND swarm_name = $2 AND caller_role = $3 AND caller_id = $4
    ORDER BY created_at ASC
    """

    events = []
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            query, task_id, swarm_name, caller_role, caller_id
        )
        for row in rows:
            events.append(
                {
                    "event": row["event_type"],
                    "data": row["event_data"],
                    "id": row["event_id"],
                }
            )

    return events


async def create_task_response(
    task_id: str,
    swarm_name: str,
    caller_role: Literal["admin", "agent", "user"],
    caller_id: str,
    response: dict[str, Any],
) -> None:
    """
    Create or update a task response record in the database.
    Uses UPSERT since each task can only have one final response.
    """
    import json

    pool = await get_pool()
    query = """
    INSERT INTO task_responses (task_id, swarm_name, caller_role, caller_id, response)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (task_id, swarm_name, caller_role, caller_id)
    DO UPDATE SET response = $5
    """

    async with pool.acquire() as connection:
        await connection.execute(
            query,
            task_id,
            swarm_name,
            caller_role,
            caller_id,
            json.dumps(response),
        )


async def load_task_responses(
    swarm_name: str,
    caller_role: Literal["admin", "agent", "user"],
    caller_id: str,
) -> dict[str, dict[str, Any]]:
    """
    Load all task responses for a given swarm, caller role, and caller ID.
    Returns a dictionary keyed by task_id.
    """
    import json

    pool = await get_pool()
    query = """
    SELECT task_id, response
    FROM task_responses
    WHERE swarm_name = $1 AND caller_role = $2 AND caller_id = $3
    """

    responses: dict[str, dict[str, Any]] = {}
    async with pool.acquire() as connection:
        rows = await connection.fetch(query, swarm_name, caller_role, caller_id)
        for row in rows:
            task_id = row["task_id"]
            response_data = row["response"]

            # Parse JSON if needed
            if isinstance(response_data, str):
                response_data = json.loads(response_data)

            responses[task_id] = response_data

    logger.info(
        f"loaded {len(responses)} task responses for {caller_role}:{caller_id}@{swarm_name}"
    )
    return responses
