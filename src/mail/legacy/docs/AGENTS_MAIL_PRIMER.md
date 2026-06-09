# AGENTS_MAIL_PRIMER — Using MAIL as a Library

Audience: developers integrating MAIL into their own codebases (not hacking MAIL internals).
Focus: programmatic use of Actions, Agents, Swarms, and Templates.

If you are developing MAIL itself, see `AGENTS.md` and `CLAUDE.md`.

## Mental Model

MAIL is an agent orchestration runtime:
- **Actions** are tool-like functions agents can call.
- **Agents** wrap an LLM call + metadata (comm targets, tool set, entrypoint/supervisor).
- **Swarms** are a set of agents + actions + runtime.

Templates vs instances:
- `MAILAction` is an action definition.
- `MAILAgentTemplate` defines how to build an agent.
- `MAILSwarmTemplate` defines a swarm (agents + actions + entrypoint).
- `MAILSwarm` is a running instance with a runtime.

Key constraints:
- Every swarm needs at least one `enable_entrypoint=True` agent (receives user messages).
- Every swarm needs at least one `can_complete_tasks=True` agent (supervisor role).
- `comm_targets` must reference valid agent names (or interswarm `agent@swarm`).

## Core Imports

```python
from mail import MAILAction, MAILAgentTemplate, MAILSwarmTemplate, action
from mail.factories import (
    LiteLLMActionAgentFunction,
    LiteLLMAgentFunction,
    LiteLLMSupervisorFunction,
)
```

## Quick Start — Minimal Swarm

```python
from mail import MAILAgentTemplate, MAILSwarmTemplate
from mail.factories import LiteLLMSupervisorFunction

supervisor = MAILAgentTemplate(
    name="supervisor",
    factory=LiteLLMSupervisorFunction,
    comm_targets=[],
    actions=[],
    agent_params={
        "llm": "anthropic/claude-sonnet-4-20250514",
        "system": "You are a helpful assistant.",
        "use_proxy": False,
    },
    enable_entrypoint=True,
    can_complete_tasks=True,
    tool_format="completions",
)

template = MAILSwarmTemplate(
    name="my_swarm",
    version="1.0.0",
    agents=[supervisor],
    actions=[],
    entrypoint="supervisor",
)

swarm = template.instantiate(
    instance_params={"user_token": "dummy"},
    user_id="local_user",
)

response, _events = await swarm.post_message_and_run(
    body="Hello!",
    subject="Greeting",
)
print(response["message"]["body"])
```

## Actions (Tools)

Actions must return a string. Two common patterns:

### 1) `@action` decorator (typed payload)

```python
from pydantic import BaseModel, Field
from mail import action

class AddArgs(BaseModel):
    a: int = Field(description="First number")
    b: int = Field(description="Second number")

@action(name="add", description="Add two numbers")
async def add(args: AddArgs) -> str:
    return str(args.a + args.b)
```

### 2) `MAILAction.from_pydantic_model` (closure-friendly)

```python
from functools import partial
from pydantic import BaseModel, Field
from mail import MAILAction

class SelectSpeakerArgs(BaseModel):
    player_name: str = Field(description="The player to speak next")

async def select_speaker(game, payload: dict) -> str:
    return game.select_speaker(payload["player_name"])

select_speaker_action = MAILAction.from_pydantic_model(
    model=SelectSpeakerArgs,
    function=partial(select_speaker, game),
    name="select_speaker",
)
```

See `src/mail/examples/mafia/narrator_tools.py` for a full pattern.

## Agents (Templates)

Use existing factories rather than rolling your own:
- `LiteLLMSupervisorFunction` for supervisors (can call `task_complete`)
- `LiteLLMActionAgentFunction` for agents that have custom actions/tools
- `LiteLLMAgentFunction` for agents with no custom actions/tools

Note: Supervisors can also have actions. If an agent is a supervisor, keep using
`LiteLLMSupervisorFunction` even when you add actions.

Key fields on `MAILAgentTemplate`:
- `name`
- `factory`
- `comm_targets` (names or interswarm `agent@swarm`)
- `actions` (list of `MAILAction`)
- `agent_params` (LLM config passed to factory)
- `enable_entrypoint` (receive user messages)
- `can_complete_tasks` (supervisor role)
- `tool_format` (top-level; "completions" or "responses")

Example (based on `MASter/src/master/prebuilt/agents.py`):

```python
supervisor = MAILAgentTemplate(
    name="supervisor",
    factory=LiteLLMSupervisorFunction,
    comm_targets=["worker"],
    actions=[],
    agent_params={
        "llm": "anthropic/claude-opus-4-5-20251101",
        "system": "System prompt here",
        "use_proxy": False,
        "stream_tokens": True,
        "reasoning_effort": "high",
        "default_tool_choice": "auto",
    },
    enable_entrypoint=True,
    can_complete_tasks=True,
    tool_format="completions",
)

worker = MAILAgentTemplate(
    name="worker",
    factory=LiteLLMActionAgentFunction,
    comm_targets=["supervisor"],
    actions=[select_speaker_action],
    agent_params={
        "llm": "anthropic/claude-opus-4-5-20251101",
        "system": "Worker prompt",
        "use_proxy": False,
        "stream_tokens": True,
    },
    tool_format="completions",
)
```

Notes:
- `tool_format` should be set at the template level. It is passed to the factory and used for action tool specs.
- OpenAI models generally use `tool_format="responses"`, Anthropic models use `"completions"`.
- If `tool_format` appears inside `agent_params`, it is ignored and a warning is logged; top-level wins.
- `comm_targets` must include valid agent names (or `agent@swarm` if interswarm is enabled).
- A swarm must have at least one `enable_entrypoint=True` and one `can_complete_tasks=True`.

## Swarms (Templates + Instances)

Build a `MAILSwarmTemplate`, then instantiate it into a runtime:

```python
from mail import MAILSwarmTemplate

swarm_template = MAILSwarmTemplate(
    name="example_swarm",
    version="1.0.0",
    agents=[supervisor, worker],
    actions=[select_speaker_action],
    entrypoint="supervisor",
)

swarm = swarm_template.instantiate(
    instance_params={"user_token": "dummy"},
    user_id="local_user",
)
```

The swarm constructor validates:
- entrypoint exists and is enabled
- comm_targets are valid
- at least one supervisor exists
- breakpoint/exclude tools are valid

## Running a Swarm

### One-off run (no continuous loop)

```python
response, events = await swarm.post_message_and_run(
    body="Hello",
    subject="New Message",
    show_events=True,
)
print(response["message"]["body"])
```

### Continuous runtime

```python
import asyncio

runtime_task = asyncio.create_task(swarm.run_continuous())

response, events = await swarm.post_message(
    body="Hello",
    subject="New Message",
    show_events=True,
)

await swarm.shutdown()
await runtime_task
```

### Streaming

```python
stream = await swarm.post_message_stream(body="Hello")
# stream is an EventSourceResponse (SSE)
```

### Manual mode (step-by-step)

`run_continuous(mode="manual")` enables manual stepping. The mafia example uses this:
`src/mail/examples/mafia/game.py`.

```python
import asyncio
import uuid

asyncio.create_task(swarm.run_continuous(mode="manual"))

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
await swarm.await_queue_empty()

response = await swarm.manual_step(
    task_id=task_id,
    target="narrator",
    response_targets=["all"],
    response_type="broadcast",
    payload="Describe the scene.",
    dynamic_ctx_ratio=0.75,
)
```

## Starting a Server (Programmatic)

`MAILSwarmTemplate.start_server()` launches a FastAPI server with your template
and optional UI dev server:

```python
swarm_template.start_server(
    port=8000,
    host="0.0.0.0",
    launch_ui=True,
    ui_port=3000,
)
```

See `../MASter/scripts/GEPA/start_eval_swarm_server.py` for a full example.

## Breakpoints + Resume

Use `breakpoint_tools` to pause execution and resume with user-supplied tool results:

```python
swarm_template = MAILSwarmTemplate(
    name="eval_swarm",
    version="1.0.0",
    agents=[supervisor, worker],
    actions=[select_speaker_action],
    entrypoint="supervisor",
    breakpoint_tools=["human_review"],
)
```

To resume:
```python
await swarm.post_message(
    body="",
    resume_from="breakpoint_tool_call",
    task_id=existing_task_id,
    breakpoint_tool_call_result={"content": "approved"},
)
```

### Parsing Breakpoint Tool Call Arguments

When a breakpoint tool is called, the response has this structure:

```python
response["message"]["subject"] == "::breakpoint_tool_call::"
response["message"]["body"] == '[{"arguments": "{...}", "name": "tool_name", "id": "call_..."}]'
```

Tool calls are standardized to OpenAI/LiteLLM format. To extract:

```python
import json

def parse_breakpoint_args(response: dict, tool_name: str) -> dict | None:
    message = response.get("message", {})
    if message.get("subject") != "::breakpoint_tool_call::":
        return None
    body = message.get("body", "")
    if not body:
        return None
    data = json.loads(body)
    # Structure: [{"arguments": "{...}", "name": "tool_name", "id": "..."}]
    for call in data:
        if call.get("name") == tool_name:
            args = call.get("arguments", "{}")
            return json.loads(args) if isinstance(args, str) else args
    return None
```

This pattern is useful for structured output: define a breakpoint tool, have the agent call it,
then extract the typed arguments instead of parsing freeform text.

## Common Patterns and Gotchas

1. `tool_format` should be a top-level template field. If it appears inside `agent_params`, it is ignored with a warning.
2. Solo agent swarms need both `enable_entrypoint=True` and `can_complete_tasks=True`.
3. Actions must return a string (serialize dicts yourself).
4. Use `functools.partial` to bind state into `MAILAction.from_pydantic_model`.
5. `dynamic_ctx_ratio` (manual step) controls how much context is reserved for dynamic history.

## Loading from swarms.json (Optional)

You can build templates from `swarms.json` (JSON array of swarms):

```python
template = MAILSwarmTemplate.from_swarm_json_file(
    swarm_name="example",
    json_filepath="swarms.json",
)
```

Note: `actions` is required in each swarm definition (use `[]` if none).

## Tool-to-Message Behavior (Quick Reference)

`send_broadcast` currently ignores `targets` and broadcasts to all agents.
`task_complete` emits a `broadcast_complete` to all agents.

## Where to Look for Real Usage

- `../MASter/src/master/prebuilt/agents.py` — agent templates and factory params
- `../MASter/scripts/GEPA/start_eval_swarm_server.py` — template + server startup
- `src/mail/examples/mafia/game.py` — building swarm templates and running manual mode
- `src/mail/examples/mafia/narrator_tools.py` — `MAILAction.from_pydantic_model` patterns
- `src/mail/examples/weather_dummy/agent.py` — `LiteLLMActionAgentFunction` usage
