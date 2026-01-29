# MAIL (Multi-Agent Interface Layer)

A multi-agent orchestration system built on an async message-passing runtime. Agents communicate via typed messages (requests, responses, broadcasts, interrupts) routed through a priority queue.

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
│   ├── action.py            # LiteLLMActionFunction - action agent (no task_complete)
│   └── supervisor.py        # LiteLLMSupervisorFunction - supervisor with task_complete
├── db/                      # PostgreSQL persistence (optional)
│   ├── utils.py             # AsyncPG pool, agent history CRUD
│   └── init.py              # Schema initialization
├── net/                     # Interswarm networking (for multi-swarm communication)
├── stdlib/                  # Pre-built actions (HTTP, MCP integrations)
├── swarms_json/             # swarms.json parsing and validation
└── examples/                # Example agent implementations
```

**Other directories:**
- `ui/` - Next.js frontend (see ui/README.md for details)
- `spec/` - MAIL protocol specification docs
- `tests/` - Test suites

## Core Concepts

### 1. MAILRuntime (`core/runtime.py`)

The heart of MAIL. An async message processor that:

- **Manages a priority queue** of messages (`asyncio.PriorityQueue`)
- **Schedules agent execution** when messages arrive
- **Maintains agent histories** - per-task, per-agent conversation context for LLM calls
- **Handles task lifecycle** - create, pause, resume, complete

**Key methods:**
- `run_task(message)` - Run a single task to completion
- `run_continuous()` - Run indefinitely, handling multiple concurrent tasks
- `submit_and_wait(message)` - Submit and wait for response (server mode)
- `submit_and_stream(message)` - Stream SSE events while processing
- `submit(message)` - Add message to queue

**Message priority (lower number = higher priority):**
- 0: Default/Admin messages (highest priority)
- 1: System messages (errors, completion signals)
- 2: User messages
- 3: Agent interrupts, broadcast_complete
- 4: Agent broadcasts
- 5: Agent requests/responses (lowest priority)

### 2. Message Types (`core/message.py`)

All messages wrapped in `MAILMessage` envelope with `id`, `timestamp`, and `msg_type`.

| Type | Purpose | Key Fields |
|------|---------|------------|
| `MAILRequest` | 1-to-1 task delegation | sender, recipient, subject, body |
| `MAILResponse` | Reply to a request | sender, recipient, subject, body |
| `MAILBroadcast` | 1-to-many notification | sender, recipients[], subject, body |
| `MAILInterrupt` | High-priority stop signal | sender, recipients[], subject, body |

**Additional msg_type values:**
- `broadcast_complete` - Uses `MAILBroadcast` payload; signals task completion to all agents
- `buffered` - Used for manual/eval mode message buffering

**Addressing:**
- `MAILAddress` has `address_type` ("admin", "agent", "system", "user") and `address` (name string)
- Local: `"supervisor"`, `"weather"`
- Interswarm: `"supervisor@other-swarm"`
- Broadcast to all: `"all"`

### 3. Agent Functions (`core/agents.py`)

```python
AgentFunction = Callable[
    [list[dict[str, Any]], str | dict[str, str]],  # (messages, tool_choice)
    Awaitable[AgentOutput]                          # (response_text, tool_calls)
]
```

**AgentCore** wraps an agent function with metadata:
- `function` - The async callable
- `comm_targets` - List of agents this agent can message
- `actions` - Dict of available action tools
- `enable_entrypoint` - Can receive user messages directly
- `can_complete_tasks` - Can call `task_complete` (supervisor role)
- `enable_interswarm` - Can message remote swarms

### 4. Tools & Actions (`core/tools.py`, `core/actions.py`)

**Built-in MAIL tools** (defined in `MAIL_TOOL_NAMES`):
- `send_request` - Send 1-to-1 message
- `send_response` - Reply to a request
- `send_broadcast` - Send to multiple agents
- `send_interrupt` - High-priority stop
- `task_complete` - Mark task done (supervisor only)
- `acknowledge_broadcast` / `ignore_broadcast` - Handle broadcasts
- `await_message` - Block until message arrives
- `help` - Get system help

**AgentToolCall** - Parsed tool call from LLM response:
- `tool_name`, `tool_args`, `tool_call_id`
- `completion` or `responses` - Raw LLM response (for history)
- `reasoning`, `preamble` - Extended thinking support

**ActionCore** - Custom action tools (non-MAIL):
- Wraps an async function with name and parameter schema
- Executed via `execute()` method

### 5. Tasks (`core/tasks.py`)

**MAILTask** tracks a discrete unit of work:
- `task_id`, `task_owner`, `task_contributors`
- `events` - List of `ServerSentEvent` for replay
- `is_running`, `completed` - State flags
- `task_message_queue` - Stashed messages for pause/resume

**Task lifecycle:**
1. User submits message with `task_id`
2. Runtime creates `MAILTask`, routes to entrypoint agent
3. Agents communicate, call tools, execute actions
4. Supervisor calls `task_complete` with final response
5. Task marked complete, response returned to user

### 6. Agent Histories

The runtime maintains `agent_histories: dict[str, list[dict]]` where keys are `{task_id}::{agent_name}`.

Messages are converted to XML format via `build_mail_xml()` and appended to the agent's history. This history is passed to the LLM on each agent invocation.

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

**mail.toml** (loaded by `config/server.py`):
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

**Environment variables:**
- `MAIL_CONFIG_PATH` - Override config file location
- `DATABASE_URL` - PostgreSQL connection string (for persistence)

## swarms.json Format

The file contains a **JSON array** of swarm definitions. Required fields: `name`, `version`, `entrypoint`, `agents`, `actions`.

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

**Factory string format:** `python::{module.path}:{ClassName}`
- Resolved at swarm instantiation time
- Can reference prompts the same way: `python::module:VARIABLE`

**Required swarm fields:** `name`, `version`, `entrypoint`, `agents`, `actions`

**Required agent fields:** `name`, `factory`, `comm_targets`, `agent_params`

**Key agent fields:**
- `factory` - Python path to agent function class
- `comm_targets` - Agents this agent can message
- `actions` - List of action names this agent can use (optional, default `[]`)
- `enable_entrypoint` - Can receive initial user message (optional, default `false`)
- `can_complete_tasks` - Can call task_complete (optional, default `false`)
- `tool_format` - "completions" or "responses" (optional, default `"responses"`) - top-level agent field
- `agent_params` - Passed to factory (llm, system prompt, etc.)

## Factories (`factories/`)

**LiteLLMAgentFunction** (`factories/base.py`):
- Wraps LiteLLM/Anthropic API calls
- Handles both "completions" and "responses" API styles
- Supports extended thinking (`thinking_budget`, `reasoning_effort`)
- Converts tool calls to `AgentToolCall` objects

**LiteLLMActionFunction** (`factories/action.py`):
- Standard agent without supervisor privileges
- Cannot call `task_complete`

**LiteLLMSupervisorFunction** (`factories/supervisor.py`):
- Extends base with supervisor tools (`task_complete`, `send_interrupt`, `send_broadcast`)
- Always has `can_complete_tasks=True`

**Common agent_params** (passed to factory):
- `llm` - Model identifier (e.g., "anthropic/claude-opus-4-5-20251101")
- `system` - System prompt (string or python:: reference)
- `use_proxy` - Whether to route through LiteLLM proxy
- `reasoning_effort` - "minimal", "low", "medium", "high"
- `thinking_budget` - Token budget for extended thinking
- `stream_tokens` - Stream output to terminal

Note: `tool_format` should be a top-level agent field. If placed in agent_params, a deprecation warning is logged.

## Server API (`server.py`)

**Key endpoints:**
- `POST /message` - Submit task (JSON body: `{body, subject?, stream?, task_id?, ...}`)
  - Set `"stream": true` in body to receive SSE events
- `GET /tasks` - List caller's tasks
- `GET /task` - Get specific task (JSON body: `{task_id}`)
- `POST /interswarm/forward` - Receive interswarm message (new task)
- `POST /interswarm/back` - Receive interswarm response
- `GET /health` - Health check
- `GET /whoami` - Auth info

**POST /message body fields:**
- `body` (required) - Message content
- `subject` - Message subject (default: "New Message")
- `msg_type` - Message type: "request", "response", "broadcast", "interrupt" (default: "request")
- `stream` - Boolean, whether to stream SSE events (default: false)
- `show_events` - Boolean, whether to return task events in response (default: false)
- `task_id` - Existing task ID for continuation
- `entrypoint` - Override default entrypoint agent
- `resume_from` - Resume type ("user_response" | "breakpoint_tool_call")
- `kwargs` - Additional args passed to runtime (e.g., breakpoint tool call results)

**Instance management:**
- MAIL instances are created per-role (admin, user, swarm)
- Lazy instantiation on first request
- Persistent across requests within role

## Database Persistence

When `enable_db_agent_histories=true` and `DATABASE_URL` is set:

**Persisted data:**
- Agent histories (conversation context)
- Tasks metadata (owner, contributors, state)
- Task events (SSE events for replay)
- Task responses (final task output)

**Key functions** (`db/utils.py`):
- `get_pool()` - Get/create AsyncPG connection pool
- `create_agent_history()` / `load_agent_histories()` - Agent history CRUD
- `create_task()` / `load_tasks()` / `update_task()` - Task CRUD
- `create_task_event()` / `load_task_events()` - Task event CRUD
- `create_task_response()` / `load_task_responses()` - Task response CRUD

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

The `type` attribute on `<from>` can be: `"admin"`, `"agent"`, `"system"`, or `"user"`.

## Tool→Message Conversion

When agents call MAIL tools, `convert_call_to_mail_message()` in `core/tools.py` converts them:

| Tool Call | Becomes | msg_type |
|-----------|---------|----------|
| `send_request(target, subject, body)` | `MAILRequest` | `"request"` |
| `send_response(target, subject, body)` | `MAILResponse` | `"response"` |
| `send_interrupt(target, subject, body)` | `MAILInterrupt` | `"interrupt"` |
| `send_broadcast(subject, body, targets)` | `MAILBroadcast` to "all" | `"broadcast"` |
| `task_complete(finish_message)` | `MAILBroadcast` to "all" | `"broadcast_complete"` |

Note: `send_broadcast` currently ignores `targets` and always broadcasts to all agents.

## Auth & Roles

Requests use **Bearer token** authentication. The server exchanges the API key with an auth service via `get_token_info()` to retrieve role and ID.

**Roles:**
- `admin` - Full access, can load swarms, health checks
- `user` - Can submit tasks, view own tasks
- `agent` - Used for interswarm communication between swarms

**Role-based endpoint access** (via FastAPI dependencies in `utils/auth.py`):
- `caller_is_admin` - Admin only
- `caller_is_user` - User only
- `caller_is_admin_or_user` - Either
- `caller_is_agent` - Agent only (interswarm endpoints)

**Per-role isolation:** The server maintains separate MAIL runtime instances per role+id combination. Tasks are bound to their creator.

## String Resolution (`utils/parsing.py`)

swarms.json supports special string prefixes that get resolved at load time:

- **`python::module.path:object`** - Imports Python object (class, function, variable)
  - Example: `"python::mail.factories.supervisor:LiteLLMSupervisorFunction"`
  - Example: `"python::mail.examples.prompts:SYSTEM_PROMPT"`
- **`url::https://...`** - Fetches URL content as JSON string
  - Example: `"url::https://example.com/config.json"`

Resolution happens via `resolve_prefixed_string_references()` which recursively processes dicts/lists.

## Breakpoint & Manual Flow

**breakpoint_tools** - List of tool names that pause execution and require user input to continue:
```json
{
  "breakpoint_tools": ["human_review", "approval_required"]
}
```

When an agent calls a breakpoint tool:
1. Task pauses, SSE event `breakpoint_tool_call` emitted
2. Queue is stashed via `queue_stash()`
3. Client must call `POST /message` with `resume_from: "breakpoint_tool_call"` and tool result in `kwargs`
4. On resume, `breakpoint_action_complete` event emitted with the result

**exclude_tools** - MAIL tools to hide from agents:
```json
{
  "exclude_tools": ["send_interrupt", "send_broadcast"]
}
```

**resume_from options** (in POST /message body):
- `"user_response"` - Resume with new user message
- `"breakpoint_tool_call"` - Resume with breakpoint tool result

## SSE Event Types

Events emitted by the runtime for streaming clients (via `_submit_event()` and `submit_and_stream()`):

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
| `builtin_tool_call` | OpenAI built-in tool invoked (web_search_call, code_interpreter_call) |
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

Events are stored in `MAILTask.events` and can be retrieved via `/task` endpoint or streamed.

## Extended Thinking Support

For models with extended thinking (Claude with `thinking_budget`):

**Factory params:**
- `reasoning_effort` - "minimal", "low", "medium", "high"
- `thinking_budget` - Token limit for thinking (e.g., 10000)

**AgentToolCall fields:**
- `reasoning` - List of thinking text blocks preceding the tool call
- `preamble` - Text content before the tool call

**pause_turn handling:** When extended thinking is active, `LiteLLMAgentFunction` (factory layer) handles `pause_turn` responses where the model signals it needs more thinking time before producing output.

## Common Gotchas

1. **`broadcast_complete` vs `broadcast`**: `task_complete` tool creates a `broadcast_complete` message (not `broadcast`). This special msg_type signals task termination and doesn't reprompt recipients.

2. **`await_message` behavior**: Blocks the agent until another message arrives. The `outstanding_requests` dict tracks pending requests per agent but doesn't prevent task completion.

3. **`tool_format` location**: Should be a **top-level agent field**. If placed inside `agent_params`, a deprecation warning is logged and the top-level value takes precedence.

4. **`actions` is required**: In swarms.json, even if empty, the `actions: []` field must be present.

5. **History key format**: Agent histories keyed by `{task_id}::{agent_name}`. If you're debugging missing context, check this key construction.

6. **Priority 0 is highest**: Lower numbers = higher priority. Admin messages default to 0, user to 2, agent messages 3-5.

7. **Interswarm addressing**: Use `agent@swarm` format. The `@` triggers interswarm routing via `parse_agent_address()`.

8. **System responses end loops**: System-to-system messages immediately terminate tasks to prevent infinite loops.

## Conventions

- **Async everywhere** - All I/O operations are async
- **XML message format** - Messages converted to XML for LLM context (`build_mail_xml`)
- **Priority queuing** - Admin (0) > System (1) > User (2) > Agent messages (3-5)
- **History key format** - `{task_id}::{agent_name}`
- **Factory pattern** - Agents created via factory strings in swarms.json
- **SSE events** - All task events emitted as ServerSentEvents for streaming

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

Uses Python's `logging` module. Key loggers:
- `mail.runtime` - Runtime operations
- `mail.factories.base` - LLM calls
- `mail.server` - HTTP server
- `mail.actions` - Action execution
