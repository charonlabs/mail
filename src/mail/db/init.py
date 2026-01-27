# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

"""
Database initialization for MAIL persistence (agent histories, tasks, events, responses).
"""

import os
import sys

import asyncpg
import dotenv


async def create_tables() -> None:
    """
    Create all MAIL persistence tables and indexes in the database.
    """
    dotenv.load_dotenv()
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set")
        print("Please set DATABASE_URL in your .env file or environment")
        print("Example: DATABASE_URL=postgresql://user:password@localhost:5432/mail")
        sys.exit(1)

    print("Connecting to database...")

    try:
        conn = await asyncpg.connect(database_url)
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}")
        sys.exit(1)

    print("Connected successfully")

    # ==========================================================================
    # Table: agent_histories
    # ==========================================================================
    create_agent_histories_sql = """
    CREATE TABLE IF NOT EXISTS agent_histories (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        swarm_name TEXT NOT NULL,
        caller_role TEXT NOT NULL,
        caller_id TEXT NOT NULL,
        tool_format TEXT NOT NULL,
        task_id TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        history JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    );
    """

    agent_histories_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_swarm_name ON agent_histories (swarm_name);",
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_task_id ON agent_histories (task_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_caller ON agent_histories (caller_role, caller_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_agent_name ON agent_histories (agent_name);",
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_created_at ON agent_histories (created_at DESC);",
    ]

    # ==========================================================================
    # Table: tasks
    # ==========================================================================
    create_tasks_sql = """
    CREATE TABLE IF NOT EXISTS tasks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        task_id TEXT NOT NULL,
        swarm_name TEXT NOT NULL,
        caller_role TEXT NOT NULL,
        caller_id TEXT NOT NULL,
        task_owner TEXT NOT NULL,
        task_contributors JSONB NOT NULL DEFAULT '[]',
        remote_swarms JSONB NOT NULL DEFAULT '[]',
        is_running BOOLEAN NOT NULL DEFAULT FALSE,
        completed BOOLEAN NOT NULL DEFAULT FALSE,
        title TEXT,
        start_time TIMESTAMP WITH TIME ZONE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        UNIQUE(task_id, swarm_name, caller_role, caller_id)
    );
    """

    tasks_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_tasks_lookup ON tasks (swarm_name, caller_role, caller_id);",
        "CREATE INDEX IF NOT EXISTS idx_tasks_task_id ON tasks (task_id);",
    ]

    # ==========================================================================
    # Table: task_events
    # ==========================================================================
    create_task_events_sql = """
    CREATE TABLE IF NOT EXISTS task_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        task_id TEXT NOT NULL,
        swarm_name TEXT NOT NULL,
        caller_role TEXT NOT NULL,
        caller_id TEXT NOT NULL,
        event_type TEXT,
        event_data TEXT,
        event_id TEXT,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    );
    """

    task_events_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_task_events_lookup ON task_events (task_id, swarm_name, caller_role, caller_id);",
        "CREATE INDEX IF NOT EXISTS idx_task_events_created ON task_events (created_at);",
    ]

    # ==========================================================================
    # Table: task_responses
    # ==========================================================================
    create_task_responses_sql = """
    CREATE TABLE IF NOT EXISTS task_responses (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        task_id TEXT NOT NULL,
        swarm_name TEXT NOT NULL,
        caller_role TEXT NOT NULL,
        caller_id TEXT NOT NULL,
        response JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        UNIQUE(task_id, swarm_name, caller_role, caller_id)
    );
    """

    task_responses_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_task_responses_lookup ON task_responses (task_id, swarm_name, caller_role, caller_id);",
    ]

    try:
        # Create agent_histories table
        print("Creating agent_histories table...")
        await conn.execute(create_agent_histories_sql)
        for idx_sql in agent_histories_indexes:
            await conn.execute(idx_sql)
        print("  agent_histories table created")

        # Create tasks table
        print("Creating tasks table...")
        await conn.execute(create_tasks_sql)
        for idx_sql in tasks_indexes:
            await conn.execute(idx_sql)
        print("  tasks table created")

        # Create task_events table
        print("Creating task_events table...")
        await conn.execute(create_task_events_sql)
        for idx_sql in task_events_indexes:
            await conn.execute(idx_sql)
        print("  task_events table created")

        # Create task_responses table
        print("Creating task_responses table...")
        await conn.execute(create_task_responses_sql)
        for idx_sql in task_responses_indexes:
            await conn.execute(idx_sql)
        print("  task_responses table created")

        # Verify tables exist
        print("\nVerifying tables...")
        tables = ["agent_histories", "tasks", "task_events", "task_responses"]
        for table_name in tables:
            result = await conn.fetchrow(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1);",
                table_name,
            )
            if result and result[0]:
                print(f"  {table_name}: OK")
            else:
                print(f"  {table_name}: MISSING")

    except Exception as e:
        print(f"ERROR: Failed to create tables: {e}")
        sys.exit(1)
    finally:
        await conn.close()

    print("\nDatabase initialization complete!")
