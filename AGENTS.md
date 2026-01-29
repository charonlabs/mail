# MAIL (Multi-Agent Interface Layer) — Codex Agent Notes

Practical onboarding doc for future Codex sessions. Mirrors `CLAUDE.md` content, but organized for fast scanning.

## Quick Start

```bash
# Install dependencies
uv sync

# Run the server
uv run mail server

# Run with custom config
MAIL_CONFIG_PATH=./mail.toml uv run mail server
```

## Project Structure

```
src/mail/
├── core/                    # Runtime and message abstractions
│   ├── runtime.py           # MAILRuntime - the async message processor (main loop)
│   ├── message.py           # Message types: MAILRequest, MAILResponse, MAILBroadcast, MAILInterrupt
│   ├── agents.py            # AgentCore - minimal agent definition
│   ├── actions.py           # ActionCore - tool/action wrapper
│   ├── tools.py             # MAIL tool definitions, AgentToolCall, tool<->message conversion
│   └── tasks.py             # MAILTask - task state, event history, queue stash/restore
├── api.py                   # High-level API: MAILSwarm, MAILSwarmTemplate, MAILAgent, MAILAction
├── server.py                # FastAPI server with HTTP endpoints and SSE streaming
├── client.py                # Async HTTP client for remote swarms
├── cli.py                   # CLI commands (mail server, mail client)
├── config/
│   └── server.py            # ServerConfig, SwarmConfig (Pydantic models from mail.toml)
├── factories/               # Agent function factories
│   ├── base.py              # LiteLLMAgentFunction - wraps LiteLLM/Anthropic API calls
│   └── supervisor.py        # LiteLLMSupervisorFunction - supervisor with task_complete
├── db/                      # PostgreSQL persistence (optional)
│   ├── utils.py             # AsyncPG pool, agent history CRUD
│   └── init.py              # Schema initialization
├── net/                     # Interswarm networking (for multi-swarm communication)
├── stdlib/                  # Pre-built actions (HTTP, MCP integrations)
├── swarms_json/             # swarms.json parsing and validation
└── examples/                # Example agent implementations
```

Other directories:
- `ui/` - Next.js frontend (see `ui/README.md`)
- `spec/` - MAIL protocol specification docs
- `tests/` - Test suites

## Core Concepts

### MAILRuntime (`core/runtime.py`)

Async message processor that:
- Manages a priority queue (`asyncio.PriorityQueue`)
- Schedules agent execution
- Maintains per-task, per-agent histories for LLM calls
- Handles task lifecycle (create/pause/resume/complete)

Key methods:
- `run_task(message)`
- `run_continuous()`
- `submit_and_wait(message)`
- `submit_and_stream(message)`
- `submit(message)`

Message priority (lower number = higher priority):
- 0: Default/Admin messages (highest priority)
- 1: System messages (errors, completion signals)
- 2: User messages
- 3: Agent interrupts, broadcast_complete
- 4: Agent broadcasts
- 5: Agent requests/responses (lowest priority)

### Message Types (`core/message.py`)

All messages are `MAILMessage` envelopes with `id`, `timestamp`, and `msg_type`.

| Type | Purpose | Key Fields |
|------|---------|------------|
| `MAILRequest` | 1-to-1 task delegation | sender, recipient, subject, body |
| `MAILResponse` | Reply to a request | sender, recipient, subject, body |
| `MAILBroadcast` | 1-to-many notification | sender, recipients[], subject, body |
| `MAILInterrupt` | High-priority stop signal | sender, recipients[], subject, body |

Additional `msg_type` values:
- `broadcast_complete` - Uses `MAILBroadcast` payload; signals task completion to all agents
- `buffered` - Used for manual/eval mode message buffering

Addressing:
- `MAILAddress`: `address_type` ("admin", "agent", "system", "user") + `address` (name string)
- Local: `"supervisor"`, `"weather"`
- Interswarm: `"supervisor@other-swarm"`
- Broadcast to all: `"all"`

### Agent Functions (`core/agents.py`)

```python
AgentFunction = Callable[
    [list[dict[str, Any]], str | dict[str, str]],  # (messages, tool_choice)
    Awaitable[AgentOutput]                          # (response_text, tool_calls)
]
```

`AgentCore` metadata:
- `function`
- `comm_targets`
- `actions`
- `enable_entrypoint`
- `can_complete_tasks`
- `enable_interswarm`

### Tools & Actions (`core/tools.py`, `core/actions.py`)

Built-in MAIL tools (`MAIL_TOOL_NAMES`):
- `send_request`
- `send_response`
- `send_broadcast`
- `send_interrupt`
- `task_complete`
- `acknowledge_broadcast` / `ignore_broadcast`
- `await_message`
- `help`

`AgentToolCall` fields:
- `tool_name`, `tool_args`, `tool_call_id`
- `completion` or `responses`
- `reasoning`, `preamble`

`ActionCore`:
- Wraps an async function with name + schema
- Executed via `execute()`

### Tasks (`core/tasks.py`)

`MAILTask` tracks:
- `task_id`, `task_owner`, `task_contributors`
- `events` (list of `ServerSentEvent`)
- `is_running`, `completed`
- `task_message_queue` (stash for pause/resume)

Task lifecycle:
1. User submits message with `task_id`
2. Runtime creates `MAILTask`, routes to entrypoint agent
3. Agents communicate, call tools, execute actions
4. Supervisor calls `task_complete`
5. Task marked complete, response returned to user

### Agent Histories

`agent_histories: dict[str, list[dict]]` keyed by `{task_id}::{agent_name}`.
Messages are converted to XML via `build_mail_xml()` and appended before each agent invocation.

## Key Files for Common Changes

| Change | Primary File(s) |
|--------|-----------------|
| Add new message type | `core/message.py`, `core/tools.py` |
| Modify agent execution flow | `core/runtime.py` (look for `_send_message`, `_process_message`) |
| Add new built-in tool | `core/tools.py` (add to `MAIL_TOOL_NAMES`, create `create_X_tool()`) |
| Change LLM call behavior | `factories/base.py` (`LiteLLMAgentFunction`) |
| Add HTTP endpoint | `server.py` |
| Modify config schema | `config/server.py` |
| Change swarm definition parsing | `swarms_json/` |

## Configuration

`mail.toml` (loaded by `config/server.py`):
```toml
[server]
port = 8000
host = "0.0.0.0"
reload = false
debug = false

[server.swarm]
name = "example-no-proxy"
source = "swarms.json"
registry_file = "registries/example-no-proxy.json"

[server.settings]
task_message_limit = 15
```

Environment variables:
- `MAIL_CONFIG_PATH` - Override config file location
- `DATABASE_URL` - PostgreSQL connection string (persistence)

## swarms.json Format

`swarms.json` is a JSON array. Required fields: `name`, `version`, `entrypoint`, `agents`, `actions`.

```json
[
  {
    "name": "example",
    "version": "1.3.2",
    "entrypoint": "supervisor",
    "enable_interswarm": true,
    "enable_db_agent_histories": true,
    "agents": [
      {
        "name": "supervisor",
        "factory": "python::mail.factories.supervisor:LiteLLMSupervisorFunction",
        "comm_targets": ["weather", "math"],
        "enable_entrypoint": true,
        "can_complete_tasks": true,
        "tool_format": "completions",
        "agent_params": {
          "llm": "anthropic/claude-opus-4-5-20251101",
          "system": "python::mail.examples.supervisor.prompts:SYSPROMPT",
          "use_proxy": false
        }
      }
    ],
    "actions": [],
    "action_imports": [
      "python::mail.examples.weather_dummy.actions:get_weather_forecast"
    ]
  }
]
```

Factory string format: `python::{module.path}:{ClassName}`
- Resolved at swarm instantiation time
- Prompts can be referenced similarly: `python::module:VARIABLE`

Required swarm fields: `name`, `version`, `entrypoint`, `agents`, `actions`
Required agent fields: `name`, `factory`, `comm_targets`, `agent_params`

Key agent fields:
- `factory` - Python path to agent function class
- `comm_targets` - Agents this agent can message
- `actions` - List of action names (optional, default `[]`)
- `enable_entrypoint` - Optional, default `false`
- `can_complete_tasks` - Optional, default `false`
- `tool_format` - Optional, default `"responses"`; **top-level agent field, not in `agent_params`**
- `agent_params` - Passed to factory (llm, system prompt, etc.)

## Factories (`factories/`)

`LiteLLMAgentFunction` (`factories/base.py`):
- LiteLLM/Anthropic API wrapper
- Handles "completions" + "responses"
- Supports extended thinking (`thinking_budget`, `reasoning_effort`)
- Converts tool calls to `AgentToolCall`

`LiteLLMSupervisorFunction` (`factories/supervisor.py`):
- Extends base with supervisor tools (`task_complete`, `send_interrupt`, `send_broadcast`)
- Always has `can_complete_tasks=True`

Common `agent_params`:
- `llm` - Model identifier (e.g., "anthropic/claude-opus-4-5-20251101")
- `system` - System prompt (string or `python::` reference)
- `use_proxy` - Whether to route through LiteLLM proxy
- `reasoning_effort` - "minimal", "low", "medium", "high"
- `thinking_budget` - Token budget for extended thinking
- `stream_tokens` - Stream output to terminal

Note: `tool_format` is top-level, not inside `agent_params`.

## Server API (`server.py`)

Key endpoints:
- `POST /message` - Submit task (JSON body: `{body, subject?, stream?, task_id?, ...}`)
  - Set `"stream": true` in body for SSE
- `GET /tasks` - List caller's tasks
- `GET /task` - Get specific task (JSON body: `{task_id}`)
- `POST /interswarm/forward` - Receive interswarm message (new task)
- `POST /interswarm/back` - Receive interswarm response
- `GET /health` - Health check
- `GET /whoami` - Auth info

`POST /message` body fields:
- `body` (required)
- `subject` (default `"New Message"`)
- `msg_type` - "request", "response", "broadcast", "interrupt" (default `"request"`)
- `stream` (default `false`)
- `show_events` (default `false`)
- `task_id` (for continuation)
- `entrypoint` (override default entrypoint)
- `resume_from` - `"user_response"` or `"breakpoint_tool_call"`
- `kwargs` - Additional args passed to runtime (e.g., breakpoint tool call results)

Instance management:
- MAIL runtimes are created per-role (admin, user, swarm)
- Lazy instantiation on first request
- Persistent across requests within role

## Database Persistence

Enabled when `enable_db_agent_histories=true` and `DATABASE_URL` is set.

Persisted data:
- Agent histories (conversation context)
- Task metadata (owner, contributors, state)
- Task events (SSE replay)
- Task responses (final output)

Key functions (`db/utils.py`):
- `get_pool()`
- `create_agent_history()` / `load_agent_histories()`
- `create_task()` / `load_tasks()` / `update_task()`
- `create_task_event()` / `load_task_events()`
- `create_task_response()` / `load_task_responses()`

## Message Flow Example

```
User: "What's the weather in Tokyo?"
    ↓
POST /message → server creates MAILRequest
    ↓
Runtime.submit() → queue.put((priority=2, seq, message))
    ↓
Main loop gets message → _process_message()
    ↓
_send_message(agent="supervisor")
  → build_mail_xml(message) → XML for LLM context
  → Append to agent_histories["task123::supervisor"]
  → Call supervisor_fn(history, tool_choice="required")
  → Returns: (None, [AgentToolCall(name="send_request", args={target:"weather"...})])
    ↓
Tool call → convert_call_to_mail_message() → MAILRequest supervisor→weather
    ↓
queue.put() → weather agent receives → calls get_weather_forecast action
    ↓
Weather responds to supervisor → supervisor calls task_complete
    ↓
broadcast_complete message → runtime marks task complete
    ↓
Response returned to user
```

## XML Message Format (What Agents See)

Messages are converted to XML via `build_mail_xml()` before being added to agent history:

```xml
<incoming_message>
<timestamp>2025-01-08T12:00:00+00:00</timestamp>
<from type="user">user_123</from>
<to>
['<address type="agent">supervisor</address>']
</to>
<subject>New Message</subject>
<body>What's the weather in Tokyo?</body>
</incoming_message>
```

`<from type>` can be: `"admin"`, `"agent"`, `"system"`, or `"user"`.

## Tool→Message Conversion

`convert_call_to_mail_message()` in `core/tools.py`:

| Tool Call | Becomes | msg_type |
|-----------|---------|----------|
| `send_request(target, subject, body)` | `MAILRequest` | `"request"` |
| `send_response(target, subject, body)` | `MAILResponse` | `"response"` |
| `send_interrupt(target, subject, body)` | `MAILInterrupt` | `"interrupt"` |
| `send_broadcast(subject, body, targets)` | `MAILBroadcast` to "all" | `"broadcast"` |
| `task_complete(finish_message)` | `MAILBroadcast` to "all" | `"broadcast_complete"` |

Note: `send_broadcast` currently ignores `targets` and always broadcasts to all agents.

## Auth & Roles

Requests use Bearer token auth. The server exchanges the API key with the auth service via `get_token_info()` to retrieve role and ID.

Roles:
- `admin` - Full access, can load swarms, health checks
- `user` - Can submit tasks, view own tasks
- `agent` - Interswarm communication

Role-based endpoint access (FastAPI deps in `utils/auth.py`):
- `caller_is_admin`
- `caller_is_user`
- `caller_is_admin_or_user`
- `caller_is_agent`

Per-role isolation: separate runtimes per role+id; tasks bound to creator.

## String Resolution (`utils/parsing.py`)

swarms.json supports string prefixes resolved at load time:
- `python::module.path:object` - import Python object
- `url::https://...` - fetch URL content as JSON string

Resolved via `resolve_prefixed_string_references()` (recursive).

## Breakpoint & Manual Flow

`breakpoint_tools` pauses execution and requires user input:
```json
{
  "breakpoint_tools": ["human_review", "approval_required"]
}
```

When a breakpoint tool is called:
1. Task pauses, SSE event `breakpoint_tool_call` emitted
2. Queue is stashed via `queue_stash()`
3. Client calls `POST /message` with `resume_from: "breakpoint_tool_call"` and tool result in `kwargs`
4. On resume, `breakpoint_action_complete` emitted with result

`exclude_tools` hides MAIL tools:
```json
{
  "exclude_tools": ["send_interrupt", "send_broadcast"]
}
```

`resume_from` options (POST /message):
- `"user_response"`
- `"breakpoint_tool_call"`

## SSE Event Types

Events emitted via `_submit_event()` and direct streaming:

| Event | When |
|-------|------|
| `action_call` | Non-MAIL action tool invoked |
| `action_complete` | Non-MAIL action tool completed |
| `action_error` | Action tool failed |
| `agent_error` | Agent tried invalid operation |
| `await_message` | Agent called await_message tool |
| `breakpoint_action_complete` | Breakpoint tool resumed with result |
| `breakpoint_tool_call` | Agent called a breakpoint tool (task paused) |
| `broadcast_ignored` | Agent ignored a broadcast |
| `builtin_tool_call` | OpenAI built-in tool invoked (web_search/code_interpreter) |
| `help_called` | Agent called help tool |
| `interswarm_message_error` | Failed to send/receive interswarm message |
| `interswarm_message_received` | Got message from remote swarm |
| `interswarm_message_sent` | Sent message to remote swarm |
| `new_message` | Message queued/delivered |
| `ping` | Streaming heartbeat |
| `run_loop_cancelled` | Runtime loop cancelled |
| `run_loop_error` | Error in runtime loop |
| `shutdown_requested` | Shutdown requested |
| `task_complete` | Task finished successfully |
| `task_complete_call` | Agent called task_complete tool |
| `task_complete_call_duplicate` | Agent called task_complete on already-complete task |
| `task_error` | Task failed (timeout, error) |
| `tool_call` | Generic tool call event |

Events are stored in `MAILTask.events` and can be retrieved via `/task` or streamed.

## Extended Thinking Support

For models with extended thinking (Claude with `thinking_budget`):
- Factory params: `reasoning_effort`, `thinking_budget`
- `AgentToolCall` fields: `reasoning`, `preamble`
- `pause_turn` handling happens in `LiteLLMAgentFunction` (factory layer)

## Common Gotchas

1. `task_complete` produces `broadcast_complete` (not `broadcast`).
2. `await_message` blocks until another message arrives; `outstanding_requests` tracks pending requests per agent but doesn’t block task completion.
3. `tool_format` must be top-level agent field (not inside `agent_params`).
4. `actions` is required in swarms.json (use `[]` if none).
5. Agent history key format: `{task_id}::{agent_name}`.
6. Priority: 0 is highest (admin), user is 2, agent 3–5.
7. Interswarm addresses use `agent@swarm`.
8. System-to-system responses terminate tasks to prevent infinite loops.

## Conventions

- Async I/O everywhere
- XML message format via `build_mail_xml()`
- Priority: Admin (0) > System (1) > User (2) > Agent (3–5)
- Histories keyed by `{task_id}::{agent_name}`
- Agents created via factory strings in swarms.json
- SSE events emitted as `ServerSentEvent`

## Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_runtime.py

# Run with coverage
uv run pytest --cov=mail
```

## Logging

Key loggers:
- `mail.runtime`
- `mail.factories.base`
- `mail.server`
- `mail.actions`
