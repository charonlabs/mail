# API Surfaces

The MAIL Python reference implementation exposes two integration layers: an **HTTP surface** for remote clients and a **Python surface** for embedding the runtime. Both surfaces operate on the same MAIL message schema defined in [src/mail/core/message.py](/src/mail/core/message.py).

## HTTP API

The server exposes a [FastAPI application](/src/mail/server.py) with endpoints for user messaging, interswarm routing, and registry management. The generated OpenAPI description lives in [spec/openapi.yaml](/spec/openapi.yaml).

### Auth
- All non-root endpoints require **`Authorization: Bearer <token>`**
- **Tokens** are validated against `TOKEN_INFO_ENDPOINT`, which must respond with `{ role, id, api_key }`
- Supported **roles**: `admin`, `user`, `agent`
- See [src/mail/utils/auth.py](/src/mail/utils/auth.py) for token helpers

### Endpoints

#### `GET /`
- basic service metadata (`name`, `version`, `status`)
#### `GET /status` 
- (admin/user)
- readiness check plus active user instance info
#### `POST /message`
- (admin/user)
- enqueue a user-scoped task; body: `{ message: string, entrypoint?: string, show_events?: bool, stream?: bool }`
- `POST /message` with `stream: true` returns SSE (see below)
#### `POST /interswarm/message`
- (agent)
- receive a `MAILInterswarmMessage` from a remote swarm and return a `MAILMessage`
#### `POST /interswarm/response`
- (agent)
- accept a `MAILMessage` response from a remote swarm
#### `POST /interswarm/send`
- (admin/user)
- `{ target_agent, message, user_token }`, forwards a direct interswarm request via the local swarm runtime
#### `GET /swarms`
- list swarms known to the local registry
- `POST /swarms` (admin) → register a swarm (volatile by default)
- `GET /swarms/dump` (admin) → dump the current registry as JSON
- `POST /swarms/load` (admin) → load persistent swarm templates from JSON into the registry

### SSE streaming
- `POST /message` with `stream: true` yields an `text/event-stream`
- Events include periodic `ping` heartbeats and a final `task_complete` event carrying the serialized response

### Error handling
- FastAPI raises standard HTTP errors with `detail` strings
- The runtime also emits structured MAIL error responses when routing fails

### Notes
- The server keeps a persistent `MAILSwarmTemplate` catalogue and per-user `MAILSwarm` instances
- Message shapes and schemas are documented in [docs/message-format.md](/docs/message-format.md) and [spec/](/spec/SPEC.md)

## Python API

The Python surface is designed for embedding MAIL inside other applications, building custom swarms, or scripting tests. The primary exports live in [src/mail/\_\_init\_\_.py](/src/mail/__init__.py) and re-export key classes from `mail.api` and `mail.core`.

### Imports and modules
- `from mail import MAILAgent, MAILAgentTemplate, MAILAction, MAILSwarm, MAILSwarmTemplate` provides the high-level builder classes
- `from mail import MAILMessage, MAILRequest, MAILResponse, MAILBroadcast, MAILInterrupt, AgentToolCall` gives the protocol types
- `mail.net` exposes `SwarmRegistry` and `InterswarmRouter` for discovery and routing helpers
- `mail.utils` bundles token helpers, logging utilities, dynamic factory loading via `read_python_string`, and interswarm address parsing

### Core builder classes (`mail.api`)

#### `MAILAction`
- Wraps a callable that can be exposed as an OpenAI tool; constructor takes `name`, `description`, a JSONSchema-like `parameters` dict, and a string pointing to an async function (`module:function`)
- `MAILAction.from_pydantic_model(model, function_str, name?, description?)` converts a Pydantic model into a tool definition automatically
- `MAILAction.to_tool_dict(style="responses"|"completions")` emits an OpenAI-compatible tool payload
- `MAILAction.to_pydantic_model(for_tools: bool = False)` returns a Pydantic class usable for validation or schema generation
- `MAILAction.from_swarm_json(json_str)` rebuilds an action from persisted swarm metadata

#### `MAILAgent`
- Concrete agent instance wired to a factory-built coroutine (`AgentFunction`) and zero or more `MAILAction`s
- Validates its `name`, communication targets, and solo-agent settings (`enable_entrypoint`, `can_complete_tasks`)
- Callable: `await agent(messages, tool_choice)` runs the agent implementation and returns `(response_text | None, list[AgentToolCall])`
- `MAILAgent._to_template(names)` trims comm targets to a provided agent subset (used by swarm templates)

#### `MAILAgentTemplate`
- Declarative agent description used for persistence and cloning
- Stores the dotted-path factory string plus default parameters and tool format (`completions` vs `responses`)
- `instantiate(instance_params)` loads the factory via `read_python_string`, merges defaults with `instance_params`, and returns a `MAILAgent`
- `from_swarm_json(json_str)` and `from_example(name, comm_targets)` bootstrap templates from JSON dumps or bundled examples under [src/mail/examples](/src/mail/examples)

### Swarm containers

#### `MAILSwarm`
- Runtime container that owns instantiated agents, actions, and an embedded `MAILRuntime`
- Key async methods: `post_message`, `post_message_stream`, `post_message_and_run`, `submit_message`, `submit_message_stream`, `run_continuous`, `start_interswarm`, `stop_interswarm`, `shutdown`
- Maintains adjacency metadata, supervisor lookup (`agent.can_complete_tasks`), and pending request futures for tracking long-running tasks
- Provides utilities such as `handle_interswarm_response`, `route_interswarm_message`, `get_subswarm`, and `get_pending_requests`

#### `MAILSwarmTemplate`
- Immutable swarm blueprint comprised of `MAILAgentTemplate`s and `MAILAction`s
- `instantiate(instance_params, user_id?, base_url?, registry_file?)` produces a `MAILSwarm`; interswarm mode creates a `SwarmRegistry` automatically
- `get_subswarm(names, name_suffix, entrypoint?)` filters agents into a smaller template while validating entrypoint and supervisor guarantees
- `from_swarm_json(json_str)` / `from_swarm_json_file(swarm_name, json_filepath?)` rebuild templates from the repository `swarms.json`

### Message type definitions (`mail.core.message`)
- `MAILAddress` → typed address `{ address_type: "agent"|"user"|"system", address: str }`
- `MAILRequest`, `MAILResponse`, `MAILBroadcast`, `MAILInterrupt` → typed dicts representing each MAIL verb, including interswarm routing metadata
- `MAILInterswarmMessage` → HTTP transport wrapper for requests, responses, broadcasts, and interrupts
- `MAILMessage` → envelope `{ id, timestamp, message, msg_type }` used throughout the runtime
- Helper constructors: `create_agent_address`, `create_user_address`, `create_system_address`, `format_agent_address`, `parse_agent_address`, plus XML builders (`build_body_xml`, `build_mail_xml`)

### Runtime utilities (`mail.core`)
- `MAILRuntime` orchestrates the async message queue, tool execution (`execute_action_tool`), persistence of events for SSE, and interswarm routing hooks. Important methods include `submit`, `submit_and_wait`, `submit_and_stream`, `run`, `run_continuous`, `start_interswarm`, and `handle_interswarm_response`
- `AgentToolCall` models the result of OpenAI tool invocations and offers `create_response_msg()` helpers
- Tool helpers in [src/mail/core/tools.py](/src/mail/core/tools.py): `MAIL_TOOL_NAMES`, `convert_call_to_mail_message`, `create_request_tool`, `create_response_tool`, `create_interrupt_tool`, `create_broadcast_tool`, `create_acknowledge_broadcast_tool`, `create_interswarm_broadcast_tool`, `create_task_complete_tool`, and `create_supervisor_tools`

### Networking and discovery (`mail.net`)
- `SwarmRegistry(local_swarm_name, local_base_url, persistence_file?)` tracks known swarms, handles persistence of non-volatile registrations, performs periodic health checks, and resolves auth tokens stored in environment variables
- `InterswarmRouter` uses the registry to route `MAILMessage` payloads to local handlers or remote swarms over HTTP. Register local handlers with `register_message_handler`, then call `route_message` and `handle_interswarm_response`
- Common data shape: `SwarmEndpoint` (defined in [src/mail/net/types.py](/src/mail/net/types.py)) captures discovery metadata

### Utility helpers (`mail.utils`)
- Auth: `login`, `get_token_info`, `extract_token_info`, `caller_is_admin|user|agent`
- Identity helpers: `generate_user_id`, `generate_agent_id`
- Logging: `init_logger`, `get_loggers`
- Factories: `read_python_string` dynamically loads `module:function` strings used by templates
- Address parsing: `target_address_is_interswarm`
- Memory stores: `get_langmem_store` returns the configured LangMem store manager

### Example: programmatic swarm assembly

```python
import asyncio

from mail import MAILAgentTemplate, MAILSwarmTemplate
from mail.examples import weather_dummy

supervisor = MAILAgentTemplate.from_example("supervisor", comm_targets=["weather"])
weather = MAILAgentTemplate.from_example("weather", comm_targets=["supervisor"])

demo_template = MAILSwarmTemplate(
    name="demo-swarm",
    agents=[supervisor, weather],
    actions=[*supervisor.actions, *weather.actions],
    entrypoint="supervisor",
)

async def main() -> None:
    swarm = demo_template.instantiate(instance_params={}, user_id="demo-user")
    response, events = await swarm.post_message(
        subject="Forecast check",
        body="What's the outlook for tomorrow in New York?",
        show_events=True,
    )
    print(response["message"]["body"])
    await swarm.shutdown()

asyncio.run(main())
```

This snippet constructs two agents from the bundled examples, wires them into a `MAILSwarmTemplate`, instantiates the swarm for a specific user, posts a request, and finally tears the runtime down.
