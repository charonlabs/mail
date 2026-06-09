# CLAUDE_MAIL_PRIMER — Using MAIL as a Library

This document is for Claude sessions building applications that use MAIL as an imported library. If you're developing MAIL itself, see `CLAUDE.md` in the repository root.

## Mental Model

MAIL is a multi-agent orchestration runtime where agents communicate via an async message queue. The core abstraction is **templates vs instances**:

```
MAILAction          → defines a tool (callable + schema)
MAILAgentTemplate   → defines how to build an agent (factory + params)
MAILSwarmTemplate   → defines a swarm (agents + actions + entrypoint)
        ↓
    .instantiate()
        ↓
MAILSwarm           → running swarm with a MAILRuntime inside
```

A `MAILSwarmTemplate` is a blueprint. Calling `.instantiate()` creates a `MAILSwarm` with an actual runtime that can process messages.

**Key constraints:**
- Every swarm needs at least one `enable_entrypoint=True` agent (can receive user messages)
- Every swarm needs at least one `can_complete_tasks=True` agent (supervisor role)
- `comm_targets` must reference valid agent names within the swarm

## Core Imports

```python
from mail import MAILAction, MAILAgentTemplate, MAILSwarmTemplate, action
from mail.factories import (
    LiteLLMAgentFunction,        # Base agent (no actions, no task_complete)
    LiteLLMActionAgentFunction,  # Agent with actions (no task_complete)
    LiteLLMSupervisorFunction,   # Supervisor (has task_complete)
)
```

## Quick Start — Minimal Working Swarm

```python
from mail import MAILAgentTemplate, MAILSwarmTemplate
from mail.factories import LiteLLMSupervisorFunction

# 1. Define an agent template
supervisor = MAILAgentTemplate(
    name="supervisor",
    factory=LiteLLMSupervisorFunction,
    comm_targets=[],  # No other agents to talk to
    actions=[],
    agent_params={
        "llm": "anthropic/claude-sonnet-4-20250514",
        "system": "You are a helpful assistant.",
        "use_proxy": False,
    },
    enable_entrypoint=True,
    can_complete_tasks=True,
    tool_format="completions",  # or "responses" for OpenAI
)

# 2. Build swarm template
template = MAILSwarmTemplate(
    name="my_swarm",
    version="1.0.0",
    agents=[supervisor],
    actions=[],
    entrypoint="supervisor",
)

# 3. Instantiate and run
swarm = template.instantiate(
    instance_params={"user_token": "dummy"},
    user_id="local_user",
)

# One-shot execution
response, events = await swarm.post_message_and_run(
    body="Hello!",
    subject="Greeting",
)
print(response["message"]["body"])
```

## Actions (Tools)

Actions are tools that agents can call. They must return a string. Two patterns:

### Pattern 1: `@action` Decorator

Use when the action is standalone and doesn't need external state.

```python
from pydantic import BaseModel, Field
from mail import action

class AddNumbersArgs(BaseModel):
    a: int = Field(description="First number")
    b: int = Field(description="Second number")

@action(name="add_numbers", description="Add two numbers together")
async def add_numbers(args: AddNumbersArgs) -> str:
    return str(args.a + args.b)

# Use in agent template:
worker = MAILAgentTemplate(
    name="worker",
    factory=LiteLLMActionAgentFunction,  # Use ActionAgent when agent has actions
    comm_targets=["supervisor"],
    actions=[add_numbers],  # Pass the decorated function directly
    agent_params={...},
)
```

### Pattern 2: `MAILAction.from_pydantic_model` with Closure

Use when the action needs access to external state (like a game object or database).

```python
from functools import partial
from pydantic import BaseModel, Field
from mail import MAILAction

class SelectPlayerArgs(BaseModel):
    player_name: str = Field(description="Name of the player to select")

async def select_player(game_state, args: dict) -> str:
    """The game_state is captured via partial()."""
    name = args["player_name"]
    game_state.current_player = name
    return f"Selected {name}"

# Create action with game state bound
def get_game_actions(game):
    return [
        MAILAction.from_pydantic_model(
            model=SelectPlayerArgs,
            function=partial(select_player, game),
            name="select_player",
        ),
    ]

# Usage
game = GameState()
actions = get_game_actions(game)

narrator = MAILAgentTemplate(
    name="narrator",
    factory=LiteLLMActionAgentFunction,  # Has actions
    comm_targets=["player1", "player2"],
    actions=actions,
    agent_params={...},
)
```

This pattern is extensively used in `src/mail/examples/mafia/narrator_tools.py`.

## Agent Templates

### Factory Selection

The key distinction is **whether the agent can call `task_complete`** (supervisor role):

- **`LiteLLMSupervisorFunction`** — For agents that can complete tasks (call `task_complete`). Use this for your entrypoint/coordinator agent. Can also have actions.
- **`LiteLLMActionAgentFunction`** — For worker agents that have actions but cannot complete tasks.
- **`LiteLLMAgentFunction`** — Base agent with no actions, cannot complete tasks. Use when the agent only communicates via MAIL messages.

### Key Template Fields

```python
MAILAgentTemplate(
    name="agent_name",                    # Unique within swarm
    factory=LiteLLMSupervisorFunction,    # Or LiteLLMAgentFunction
    comm_targets=["other_agent"],         # Who this agent can message
    actions=[my_action],                  # List of MAILAction objects
    agent_params={                        # Passed to factory
        "llm": "anthropic/claude-sonnet-4-20250514",
        "system": "System prompt here",
        "use_proxy": False,
        "stream_tokens": True,            # Stream to terminal
        "reasoning_effort": "high",       # For extended thinking
        "default_tool_choice": "auto",    # Tool choice override
    },
    enable_entrypoint=True,               # Can receive user messages
    can_complete_tasks=True,              # Can call task_complete
    tool_format="completions",            # "completions" or "responses"
    exclude_tools=[],                     # MAIL tools to hide
)
```

**Note:** `tool_format` should be a top-level template field. OpenAI models use `"responses"`, Anthropic models use `"completions"`.

### Multi-Agent Example

```python
supervisor = MAILAgentTemplate(
    name="supervisor",
    factory=LiteLLMSupervisorFunction,
    comm_targets=["researcher", "coder"],
    actions=[],
    agent_params={
        "llm": "anthropic/claude-sonnet-4-20250514",
        "system": "You coordinate research and coding tasks.",
        "use_proxy": False,
    },
    enable_entrypoint=True,
    can_complete_tasks=True,
    tool_format="completions",
)

researcher = MAILAgentTemplate(
    name="researcher",
    factory=LiteLLMActionAgentFunction,  # Has actions
    comm_targets=["supervisor"],
    actions=[web_search_action],
    agent_params={
        "llm": "anthropic/claude-sonnet-4-20250514",
        "system": "You search the web and report findings.",
        "use_proxy": False,
    },
    tool_format="completions",
)

coder = MAILAgentTemplate(
    name="coder",
    factory=LiteLLMActionAgentFunction,  # Has actions
    comm_targets=["supervisor"],
    actions=[run_code_action],
    agent_params={
        "llm": "anthropic/claude-sonnet-4-20250514",
        "system": "You write and execute code.",
        "use_proxy": False,
    },
    tool_format="completions",
)
```

## Swarm Templates

```python
template = MAILSwarmTemplate(
    name="my_swarm",
    version="1.0.0",
    agents=[supervisor, researcher, coder],
    actions=[web_search_action, run_code_action],  # All actions used by any agent
    entrypoint="supervisor",                        # Must have enable_entrypoint=True
    breakpoint_tools=[],                            # Tools that pause execution
    exclude_tools=[],                               # MAIL tools to hide from all agents
)
```

The swarm template validates:
- Entrypoint agent exists and has `enable_entrypoint=True`
- At least one agent has `can_complete_tasks=True`
- All `comm_targets` reference valid agent names
- All breakpoint tools exist

## Running Swarms

### One-Shot Execution

Best for simple request-response patterns:

```python
swarm = template.instantiate({"user_token": "dummy"}, "user_123")

response, events = await swarm.post_message_and_run(
    body="What's 2 + 2?",
    subject="Math Question",
    show_events=True,  # Include SSE events
)

print(response["message"]["body"])  # Final answer
```

### Continuous Mode

Best for persistent swarms that handle multiple tasks:

```python
swarm = template.instantiate({"user_token": "dummy"}, "user_123")

# Start continuous processing in background
asyncio.create_task(swarm.run_continuous())

# Submit tasks (runtime handles queue)
response, events = await swarm.post_message(
    body="First task",
    subject="Task 1",
)

response2, events2 = await swarm.post_message(
    body="Second task",
    subject="Task 2",
)

# Shutdown when done
await swarm.shutdown()
```

### Streaming

```python
stream = await swarm.post_message_stream(body="Hello")
# Returns EventSourceResponse - use in FastAPI endpoint
```

### Starting a Server

`MAILSwarmTemplate` has a convenience method to launch a FastAPI server with optional UI:

```python
template.start_server(
    port=8000,
    host="0.0.0.0",
    launch_ui=True,   # Starts Next.js dev server
    ui_port=3000,
    open_browser=True,
)
```

See `../MASter/scripts/GEPA/start_eval_swarm_server.py` for a complete example.

## Manual Mode

Manual mode gives you fine-grained control over agent stepping. This is useful for turn-based games, simulations, or debugging.

```python
# Start swarm in manual mode
swarm = template.instantiate({"user_token": "dummy"}, "game_session")
asyncio.create_task(swarm.run_continuous(mode="manual"))

# Initialize a task
task_id = str(uuid.uuid4())
init_msg = swarm.build_message(
    subject="::init::",
    body="Game starting",
    targets=["all"],
    sender_type="user",
    type="broadcast",
    task_id=task_id,
)
await swarm.submit_message_nowait(init_msg)

# Manually step specific agents
response = await swarm.manual_step(
    task_id=task_id,
    target="narrator",                # Agent to invoke
    response_targets=["all"],         # Who receives the response
    response_type="broadcast",        # "broadcast", "response", or "request"
    payload="Describe the scene.",    # Additional context for this step
)

# Step another agent
response = await swarm.manual_step(
    task_id=task_id,
    target="player1",
    response_targets=["narrator"],
    response_type="response",
    payload="What do you do?",
)
```

The mafia example (`src/mail/examples/mafia/game.py`) demonstrates this pattern extensively.

## Breakpoints — Pausing and Resuming

Breakpoint tools pause execution and return control to the caller:

```python
template = MAILSwarmTemplate(
    name="approval_swarm",
    version="1.0.0",
    agents=[...],
    actions=[human_review_action],
    entrypoint="supervisor",
    breakpoint_tools=["human_review"],  # This tool pauses execution
)

swarm = template.instantiate(...)

# Initial request
response, events = await swarm.post_message_and_run(
    body="Please process this document",
    task_id="task_123",
)

# If agent called human_review, task pauses and returns
# Response will indicate breakpoint was hit

# Resume with user-provided result
response, events = await swarm.post_message_and_run(
    body="",
    task_id="task_123",
    resume_from="breakpoint_tool_call",
    breakpoint_tool_call_result={"content": "Approved"},
)
```

### Parsing Breakpoint Tool Call Arguments

When a breakpoint tool is called, the response structure looks like this:

```python
response = {
    "message": {
        "subject": "::breakpoint_tool_call::",  # Indicates breakpoint was hit
        "body": "[{\"arguments\": \"{\\\"field\\\": \\\"value\\\"}\", \"name\": \"tool_name\", \"id\": \"call_...\"}]"
    }
}
```

Tool calls are standardized to OpenAI/LiteLLM format (arguments as JSON string). To extract:

```python
import json

def parse_breakpoint_tool_call(response: dict, tool_name: str) -> dict | None:
    """Extract tool call arguments from a breakpoint response."""
    message = response.get("message", {})
    subject = message.get("subject", "")
    body = message.get("body", "")

    if subject != "::breakpoint_tool_call::" or not body:
        return None

    body_data = json.loads(body)

    # Structure: [{"arguments": "{...}", "name": "tool_name", "id": "..."}]
    if isinstance(body_data, list) and len(body_data) > 0:
        for call in body_data:
            if call.get("name") == tool_name:
                args = call.get("arguments", "{}")
                # Arguments is a JSON string, parse it
                if isinstance(args, str):
                    return json.loads(args)
                return args

    return None
```

This pattern is useful for **structured output** scenarios where you want the LLM to call a tool with specific parameters rather than outputting freeform text.

## Common Patterns and Gotchas

### 1. `tool_format` Location

`tool_format` should be a top-level field on the agent template, not inside `agent_params`:

```python
MAILAgentTemplate(
    ...
    tool_format="completions",  # Top-level field (preferred)
    agent_params={...},         # Don't put tool_format here
)
```

If `tool_format` is found inside `agent_params`, a deprecation warning is logged and the top-level value takes precedence.

### 2. Solo Agent Swarm

A swarm with one agent needs both `enable_entrypoint=True` AND `can_complete_tasks=True`:

```python
solo = MAILAgentTemplate(
    name="solo",
    factory=LiteLLMSupervisorFunction,
    comm_targets=[],  # Empty is OK for solo
    actions=[],
    agent_params={...},
    enable_entrypoint=True,
    can_complete_tasks=True,
)
```

### 3. Action Must Return String

```python
# Wrong
async def my_action(args: dict) -> dict:
    return {"result": 123}

# Correct
async def my_action(args: dict) -> str:
    return json.dumps({"result": 123})
```

### 4. Closing Over State with `functools.partial`

```python
async def do_thing(state, args: dict) -> str:
    state.counter += 1
    return f"Count: {state.counter}"

# Create action with state bound
action = MAILAction.from_pydantic_model(
    model=DoThingArgs,
    function=partial(do_thing, my_state_object),
    name="do_thing",
)
```

### 5. OpenAI vs Anthropic `tool_format`

- OpenAI models: `tool_format="responses"`
- Anthropic models: `tool_format="completions"`

If you see tool parsing errors, check this first.

### 6. Waiting for Queue to Empty

In manual mode, wait for messages to be processed before stepping:

```python
await swarm.await_queue_empty()
response = await swarm.manual_step(...)
```

### 7. Dynamic Context Ratio

When using `manual_step`, the `dynamic_ctx_ratio` parameter (0.0-1.0) controls how much of the agent's context window is reserved for conversation history vs. static content:

```python
await swarm.manual_step(
    task_id=task_id,
    target="agent",
    dynamic_ctx_ratio=0.75,  # 75% for dynamic content
    ...
)
```

## Quick Reference

| What you want | How to do it |
|---------------|--------------|
| Define a tool | `@action` decorator or `MAILAction.from_pydantic_model()` |
| Define an agent | `MAILAgentTemplate(...)` |
| Define a swarm | `MAILSwarmTemplate(...)` |
| Create runnable swarm | `template.instantiate(params, user_id)` |
| One-shot task | `await swarm.post_message_and_run(body=...)` |
| Persistent runtime | `asyncio.create_task(swarm.run_continuous())` |
| Manual stepping | `swarm.run_continuous(mode="manual")` then `swarm.manual_step(...)` |
| Pause on tool call | Add tool name to `breakpoint_tools` |
| Resume from pause | `resume_from="breakpoint_tool_call"` |
| Stream events | `await swarm.post_message_stream(...)` |
| Launch server + UI | `template.start_server(port=8000, launch_ui=True)` |

## Example Files Worth Reading

| File | What it demonstrates |
|------|---------------------|
| `src/mail/examples/mafia/game.py` | Manual mode, complex game loop |
| `src/mail/examples/mafia/narrator_tools.py` | `MAILAction.from_pydantic_model` with closures |
| `../MASter/src/master/prebuilt/agents.py` | Agent template factory patterns |
| `../MASter/scripts/GEPA/start_eval_swarm_server.py` | Server startup with template |
