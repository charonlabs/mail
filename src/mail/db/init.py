# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

"""
Database initialization for MAIL agent history persistence.
"""

import os
import sys

import asyncpg
import dotenv


async def create_tables() -> None:
    """
    Create the agent_histories table and indexes in the database.
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

    # Create agent_histories table
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

    # Create indexes for common queries
    create_indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_swarm_name ON agent_histories (swarm_name);",
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_task_id ON agent_histories (task_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_caller ON agent_histories (caller_role, caller_id);",
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_agent_name ON agent_histories (agent_name);",
        "CREATE INDEX IF NOT EXISTS idx_agent_histories_created_at ON agent_histories (created_at DESC);",
    ]

    try:
        print("Creating agent_histories table...")
        await conn.execute(create_agent_histories_sql)
        print("Table created successfully")

        print("Creating indexes...")
        for idx_sql in create_indexes_sql:
            await conn.execute(idx_sql)
        print("Indexes created successfully")

        # Verify table exists
        result = await conn.fetchrow(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'agent_histories');"
        )
        if result and result[0]:
            print("\nVerification: agent_histories table exists")
        else:
            print("\nWARNING: Table verification failed")

    except Exception as e:
        print(f"ERROR: Failed to create tables: {e}")
        sys.exit(1)
    finally:
        await conn.close()

    print("\nDatabase initialization complete!")
