# Database Persistence

MAIL supports optional PostgreSQL persistence for agent histories, task state, and event timelines. When enabled, the runtime automatically saves and restores conversation context, allowing tasks to survive server restarts and enabling audit trails.

## Features

- **Agent History Persistence**: Conversation histories are saved per task and agent, enabling context recovery across sessions
- **Task State Tracking**: Task metadata (owner, contributors, running status, completion) persists to the database
- **Event Timeline Storage**: SSE events are recorded for debugging and replay
- **Task Response Caching**: Final responses are stored for retrieval without re-execution
- **Automatic Recovery**: On instance startup, the runtime loads existing histories and tasks from the database

## Setup

### Prerequisites

- PostgreSQL 12+ (with `gen_random_uuid()` support)
- The `DATABASE_URL` environment variable set to a valid connection string

### 1. Configure the Connection

Set the `DATABASE_URL` environment variable:

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/mail
```

The connection string format follows the standard PostgreSQL URI scheme:
```
postgresql://[user[:password]@][host][:port]/database
```

### 2. Initialize the Schema

Run the database initialization command to create all required tables:

```bash
uv run mail db-init
```

This creates four tables:

| Table | Purpose |
|-------|---------|
| `agent_histories` | Stores LLM conversation histories keyed by swarm, caller, task, and agent |
| `tasks` | Tracks task metadata including owner, contributors, status, and timestamps |
| `task_events` | Records SSE events (type, data, ID) for each task |
| `task_responses` | Caches final task responses for retrieval |

The command also creates indexes for efficient queries and verifies table creation.

### 3. Verify the Setup

After initialization, you should see output like:

```
Connecting to database...
Connected successfully
Creating agent_histories table...
  agent_histories table created
Creating tasks table...
  tasks table created
Creating task_events table...
  task_events table created
Creating task_responses table...
  task_responses table created

Verifying tables...
  agent_histories: OK
  tasks: OK
  task_events: OK
  task_responses: OK

Database initialization complete!
```

## Schema Reference

### agent_histories

```sql
CREATE TABLE agent_histories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    swarm_name TEXT NOT NULL,
    caller_role TEXT NOT NULL,      -- 'admin', 'agent', or 'user'
    caller_id TEXT NOT NULL,
    tool_format TEXT NOT NULL,      -- 'completions' or 'responses'
    task_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    history JSONB NOT NULL,         -- LLM message history
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### tasks

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id TEXT NOT NULL,
    swarm_name TEXT NOT NULL,
    caller_role TEXT NOT NULL,
    caller_id TEXT NOT NULL,
    task_owner TEXT NOT NULL,
    task_contributors JSONB DEFAULT '[]',
    remote_swarms JSONB DEFAULT '[]',
    is_running BOOLEAN DEFAULT FALSE,
    completed BOOLEAN DEFAULT FALSE,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(task_id, swarm_name, caller_role, caller_id)
);
```

### task_events

```sql
CREATE TABLE task_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id TEXT NOT NULL,
    swarm_name TEXT NOT NULL,
    caller_role TEXT NOT NULL,
    caller_id TEXT NOT NULL,
    event_type TEXT,
    event_data TEXT,
    event_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### task_responses

```sql
CREATE TABLE task_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id TEXT NOT NULL,
    swarm_name TEXT NOT NULL,
    caller_role TEXT NOT NULL,
    caller_id TEXT NOT NULL,
    response JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(task_id, swarm_name, caller_role, caller_id)
);
```

## Runtime Behavior

When `DATABASE_URL` is set:

1. **On Instance Startup**: The runtime loads agent histories and task records for the current swarm and caller. This allows resuming conversations where they left off.

2. **During Task Execution**: Agent histories are periodically saved to the database. Task state updates (running, completed) are persisted.

3. **On Task Completion**: The final response and all events are saved to the database.

4. **Connection Pooling**: The runtime uses `asyncpg` connection pooling (5-20 connections) with automatic retry logic for transient failures.

## Disabling Persistence

To run without database persistence, simply don't set `DATABASE_URL`. The runtime will operate entirely in-memory, which is suitable for development or stateless deployments.

## Troubleshooting

### Connection Errors

If you see `DATABASE_URL is not set`:
- Verify the environment variable is exported
- Check that the value is a valid PostgreSQL connection string

If connection fails:
- Verify PostgreSQL is running and accessible
- Check credentials and database name
- Ensure the database exists (create with `createdb mail` if needed)

### Missing Tables

If you see "table does not exist" errors:
- Run `mail db-init` to create the schema
- Verify the init command completed successfully

### Permission Issues

Ensure the database user has:
- `CREATE TABLE` permission (for initialization)
- `SELECT`, `INSERT`, `UPDATE` permissions (for runtime)

## Related Documentation

- [Configuration](./configuration.md) - Environment variables and `mail.toml`
- [CLI](./cli.md) - The `mail db-init` command
- [Architecture](./architecture.md) - How the runtime manages state
