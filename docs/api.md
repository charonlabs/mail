# API Surfaces

The MAIL Python reference implementation exposes two integration layers: an **HTTP surface** for remote clients and a **Python surface** for embedding the runtime. Both surfaces operate on the same MAIL message schema defined in [src/mail/core/message.py](/src/mail/core/message.py).

## HTTP API

The server exposes a [FastAPI application](/src/mail/server.py) with endpoints for **user messaging**, **interswarm routing**, and **registry management**. The generated OpenAPI description lives in [spec/openapi.yaml](/spec/openapi.yaml).

### Auth model
- **All non-root endpoints** require `Authorization: Bearer <token>`
- **Tokens** are validated against `TOKEN_INFO_ENDPOINT`, which must respond with `{ role, id, api_key }`
- Supported **roles** map to helpers in [src/mail/utils/auth.py](/src/mail/utils/auth.py): `caller_is_admin`, `caller_is_user`, `caller_is_agent`, and `caller_is_admin_or_user`

### Endpoint reference

| Method | Path | Auth required | Request body | Response body | Summary |
| --- | --- | --- | --- | --- | --- |
| GET | `/` | None (public) | `None` | `types.GetRootResponse { name, status, version }` | Returns MAIL service metadata and version string |
| GET | `/status` | `Bearer` token with role `admin` or `user` | `None` | `types.GetStatusResponse { swarm, active_users, user_mail_ready, user_task_running }` | Reports persistent swarm readiness and whether the caller already has a running runtime |
| POST | `/message` | `Bearer` token with role `admin` or `user` | `JSON { message: str, entrypoint?: str, show_events?: bool, stream?: bool }` | `types.PostMessageResponse { response: str, events?: list[ServerSentEvent] }` (or `text/event-stream` when `stream: true`) | Queues a user-scoped task, optionally returning runtime events or an SSE stream |
| GET | `/health` | None (public) | `None` | `types.GetHealthResponse { status, swarm_name, timestamp }` | Liveness signal used for interswarm discovery |
| GET | `/swarms` | None (public) | `None` | `types.GetSwarmsResponse { swarms: list[types.SwarmEndpoint] }` | Lists swarms known to the local registry |
| POST | `/swarms` | `Bearer` token with role `admin` | `JSON { name: str, base_url: str, auth_token?: str, metadata?: dict, volatile?: bool }` | `types.PostSwarmsResponse { status, swarm_name }` | Registers a remote swarm (persistent when `volatile` is `False`) |
| GET | `/swarms/dump` | `Bearer` token with role `admin` | `None` | `types.GetSwarmsDumpResponse { status, swarm_name }` | Logs the configured persistent swarm and returns acknowledgement |
| POST | `/interswarm/message` | `Bearer` token with role `agent` | `MAILInterswarmMessage { message_id, source_swarm, target_swarm, payload, ... }` | `MAILMessage` (task response) | Routes an inbound interswarm request into the local runtime and returns the generated response |
| POST | `/interswarm/response` | `Bearer` token with role `agent` | `MAILMessage { id, msg_type, message }` | `types.PostInterswarmResponseResponse { status, task_id }` | Injects a remote swarm response into the pending task queue |
| POST | `/interswarm/send` | `Bearer` token with role `admin` or `user` | `JSON { target_agent: str, message: str, user_token: str }` | `types.PostInterswarmSendResponse { response: MAILMessage, events?: list[ServerSentEvent] }` | Sends an outbound interswarm request using an existing user runtime |
| POST | `/swarms/load` | `Bearer` token with role `admin` | `JSON { json: str }` (serialized swarm template) | `types.PostSwarmsLoadResponse { status, swarm_name }` | Replaces the persistent swarm template using a JSON document |

### SSE streaming
- `POST /message` with `stream: true` yields a `text/event-stream`
- **Events** include periodic `ping` heartbeats and terminate with `task_complete` carrying the final serialized response

### Error handling
- FastAPI raises **standard HTTP errors** with a `detail` field
- The runtime emits **structured MAIL error responses** when routing or execution fails

### Notes
- The server keeps a persistent `MAILSwarmTemplate` catalogue and per-user `MAILSwarm` instances
- **Message schemas** are documented in [docs/message-format.md](/docs/message-format.md) and [spec/](/spec/SPEC.md)

## Python API

The Python surface is designed for embedding MAIL inside other applications, building custom swarms, or scripting tests. The primary exports live in [src/mail/\_\_init\_\_.py](/src/mail/__init__.py) and re-export key classes from `mail.api` and `mail.core`.

### Imports and modules
- To obtain **high-level builder classes**:
  ```python 
  from mail import MAILAgent, MAILAgentTemplate, MAILAction, MAILSwarm, MAILSwarmTemplate
  ``` 
- To obtain **protocol types**:
  ```python
  from mail import MAILMessage, MAILRequest, MAILResponse, MAILBroadcast, MAILInterrupt AgentToolCall
  ```
- To obtain **network helpers** for interswarm support:
  ```python
  from mail.net import SwarmRegistry, InterswarmRouter
- `mail.utils` bundles token helpers, logging utilities, dynamic factory loading via `read_python_string`, and interswarm address parsing

### Class reference

#### `MAILAction` (`mail.api`)
- **Summary**: Describes an action/tool exposed by an agent; wraps a callable with metadata for OpenAI tools.
- **Constructor parameters**: `name: str`, `description: str`, `parameters: dict[str, Any]` (JSONSchema-like), `function: str` (dotted `module:function`).
- **Key methods**:
  - `from_pydantic_model(model, function_str, name?, description?) -> MAILAction`: build from a Pydantic model definition.
  - `from_swarm_json(json_str) -> MAILAction`: rebuild from persisted `swarms.json` entries.
  - `to_tool_dict(style="responses"|"completions") -> dict[str, Any]`: emit an OpenAI-compatible tool declaration.
  - `to_pydantic_model(for_tools: bool = False) -> type[BaseModel]`: create a Pydantic model for validation or schema reuse.
  - `_validate() -> None` and `_build_action_function(function) -> ActionFunction`: internal guards and loader utilities.

#### `MAILAgent` (`mail.api`)
- **Summary**: Concrete runtime agent produced by an agent factory and associated actions.
- **Constructor parameters**: `name: str`, `factory: str`, `actions: list[MAILAction]`, `function: AgentFunction`, `comm_targets: list[str]`, `agent_params: dict[str, Any]`, `enable_entrypoint: bool = False`, `enable_interswarm: bool = False`, `can_complete_tasks: bool = False`, `tool_format: Literal["completions", "responses"] = "responses"`.
- **Key methods**:
  - `__call__(messages, tool_choice="required") -> Awaitable[tuple[str | None, list[AgentToolCall]]]`: execute the agent implementation.
  - `_to_template(names: list[str]) -> MAILAgentTemplate`: internal helper that trims targets for sub-swarms.
  - `_validate() -> None`: internal guard ensuring agent metadata is coherent.

#### `MAILAgentTemplate` (`mail.api`)
- **Summary**: Declarative agent description used for persistence, cloning, and factory instantiation.
- **Constructor parameters**: `name: str`, `factory: str`, `comm_targets: list[str]`, `actions: list[MAILAction]`, `agent_params: dict[str, Any]`, `enable_entrypoint: bool = False`, `enable_interswarm: bool = False`, `can_complete_tasks: bool = False`, `tool_format: Literal["completions", "responses"] = "responses"`.
- **Key methods**:
  - `instantiate(instance_params: dict[str, Any]) -> MAILAgent`: load the factory and produce a concrete `MAILAgent`.
  - `from_swarm_json(json_str) -> MAILAgentTemplate`: rebuild from `swarms.json` entries.
  - `from_example(name, comm_targets) -> MAILAgentTemplate`: load bundled examples (`supervisor`, `weather`, `math`, `consultant`, `analyst`).
  - `_top_level_params() -> dict[str, Any]` and `_validate() -> None`: internal helpers used during instantiation and validation.

#### `MAILSwarm` (`mail.api`)
- **Summary**: Runtime container that owns instantiated agents/actions and embeds a `MAILRuntime`.
- **Constructor parameters**: `name: str`, `agents: list[MAILAgent]`, `actions: list[MAILAction]`, `entrypoint: str`, `user_id: str = "default_user"`, `swarm_registry: SwarmRegistry | None = None`, `enable_interswarm: bool = False`.
- **Key methods**:
  - `post_message(...)`, `post_message_stream(...)`, `post_message_and_run(...)`: enqueue user requests (optionally streaming or running to completion).
  - `submit_message(...)`, `submit_message_stream(...)`: submit fully-formed `MAILMessage` envelopes.
  - `run_continuous(action_override: ActionOverrideFunction | None = None) -> Awaitable[None]`: long-running loop for user sessions.
  - `shutdown()`, `start_interswarm()`, `stop_interswarm()`, `is_interswarm_running()`: lifecycle and interswarm controls.
  - `handle_interswarm_response(response_message) -> Awaitable[None]`: process responses from remote swarms.
  - `route_interswarm_message(message) -> Awaitable[MAILMessage]`: send outbound interswarm traffic via the router.
  - `get_pending_requests() -> dict[str, asyncio.Future[MAILMessage]]`: inspect outstanding requests per task.
  - `get_subswarm(names, name_suffix, entrypoint?) -> MAILSwarmTemplate`: derive a sub-template focused on a subset of agents.
  - `build_message(subject, body, targets, sender_type?, type?) -> MAILMessage`: utility for crafting MAIL envelopes.

#### `MAILSwarmTemplate` (`mail.api`)
- **Summary**: Immutable swarm blueprint comprised of `MAILAgentTemplate`s and shared actions.
- **Constructor parameters**: `name: str`, `agents: list[MAILAgentTemplate]`, `actions: list[MAILAction]`, `entrypoint: str`, `enable_interswarm: bool = False`.
- **Key methods**:
  - `instantiate(instance_params, user_id?, base_url?, registry_file?) -> MAILSwarm`: produce a runtime swarm (creates `SwarmRegistry` when interswarm is enabled).
  - `get_subswarm(names, name_suffix, entrypoint?) -> MAILSwarmTemplate`: filter agents into a smaller template while preserving supervisors and entrypoints.
  - `from_swarm_json(json_str) -> MAILSwarmTemplate` / `from_swarm_json_file(swarm_name, json_filepath?) -> MAILSwarmTemplate`: rebuild from persisted JSON.
  - `_build_adjacency_matrix() -> tuple[list[list[int]], list[str]]`, `_validate() -> None`: internal helpers.

#### `AgentToolCall` (`mail.core.tools`)
- **Summary**: Pydantic model capturing the outcome of an OpenAI tool invocation.
- **Fields**: `tool_name: str`, `tool_args: dict[str, Any]`, `tool_call_id: str`, `completion: dict[str, Any]`, `responses: list[dict[str, Any]]`.
- **Key methods**:
  - `create_response_msg(content: str) -> dict[str, str]`: format a response payload for completions or responses API.
  - `model_validator` (after-init) enforces that either `completion` or `responses` is populated.

#### `MAILRuntime` (`mail.core.runtime`)
- **Summary**: Asynchronous runtime that owns the internal message queue, tool execution, and optional interswarm router.
- **Constructor parameters**: `agents: dict[str, AgentFunction]`, `actions: dict[str, ActionFunction]`, `user_id: str`, `swarm_name: str = "example"`, `swarm_registry: SwarmRegistry | None = None`, `enable_interswarm: bool = False`, `entrypoint: str = "supervisor"`.
- **Key methods**:
  - `start_interswarm()`, `stop_interswarm()`, `is_interswarm_running()`.
  - `handle_interswarm_response(response_message)` and internal `_handle_local_message(message)`.
  - `run()` and `run_continuous(action_override?)`: main scheduling loops.
  - `submit(message)`, `submit_and_wait(message, timeout)`, `submit_and_stream(message, timeout)`: queue management helpers.
  - `shutdown()` (and `_graceful_shutdown()`) for orderly teardown.
  - `get_events_by_task_id(task_id) -> list[ServerSentEvent]`: retrieve accumulated SSE events.
  - Attributes such as `pending_requests`, `events`, and `response_queue` expose runtime state.

#### `SwarmRegistry` (`mail.net.registry`)
- **Summary**: Tracks known swarm endpoints, performs health checks, and persists non-volatile registrations.
- **Constructor parameters**: `local_swarm_name: str`, `local_base_url: str`, `persistence_file: str | None = None`.
- **Key methods**:
  - `register_local_swarm(base_url)`, `register_swarm(...)`, `unregister_swarm(swarm_name)`.
  - `get_swarm_endpoint(swarm_name)`, `get_resolved_auth_token(swarm_name)`, `get_all_endpoints()`, `get_active_endpoints()`, `get_persistent_endpoints()`.
  - `save_persistent_endpoints()`, `load_persistent_endpoints()`, `cleanup_volatile_endpoints()`.
  - `start_health_checks()`, `stop_health_checks()`, `discover_swarms(discovery_urls)`: manage background discovery and health loops.
  - Utility helpers for token handling: `_get_auth_token_ref`, `_resolve_auth_token_ref`, `migrate_auth_tokens_to_env_refs`, `validate_environment_variables()`.
  - Serialization helpers: `to_dict()`.

#### `InterswarmRouter` (`mail.net.router`)
- **Summary**: HTTP router that pushes MAIL messages to local handlers or remote swarms using the registry.
- **Constructor parameters**: `swarm_registry: SwarmRegistry`, `local_swarm_name: str`.
- **Key methods**:
  - `start()` / `stop()` / `is_running()` manage the shared `aiohttp` session.
  - `register_message_handler(message_type, handler)` wires local callbacks.
  - `route_message(message) -> Awaitable[MAILMessage]`: choose local vs remote delivery.
  - Internal helpers `_route_to_local_agent`, `_route_to_remote_swarm`, `_create_local_message`, `_create_remote_message`, `_system_router_message` support routing decisions.

### Message typed dictionaries (`mail.core.message`)

#### `MAILAddress`
```python
{ 
    address_type: Literal["agent", "user", "system"], 
    address: str 
}
```
#### `MAILRequest`
```python
{ 
    task_id: str,
    request_id: str,
    sender: MAILAddress,
    recipient: MAILAddress,
    subject: str,
    body: str,
    sender_swarm: str | None,
    recipient_swarm: str | None,
    routing_info: dict[str, Any] | None 
}
```
#### `MAILResponse`
```python
{ 
    task_id: str,
    request_id: str,
    sender: MAILAddress,
    recipient: MAILAddress, 
    subject: str, 
    body: str,
    sender_swarm: str | None,
    recipient_swarm: str | None,
    routing_info: dict[str, Any] | None 
}
```
#### `MAILBroadcast`
```python
{
    task_id: str, 
    broadcast_id: str, 
    sender: MAILAddress, 
    recipients: list[MAILAddress],
    subject: str,
    body: str,
    sender_swarm: str | None,
    recipient_swarms: list[str] | None,
    routing_info: dict[str, Any] | None 
}
```
#### `MAILInterrupt`
```python
{ 
    task_id: str,
    interrupt_id: str,
    sender: MAILAddress,
    recipients: list[MAILAddress],
    subject: str,
    body: str,
    sender_swarm: str | None,
    recipient_swarms: list[str] | None,
    routing_info: dict[str, Any] | None 
}
```
#### `MAILInterswarmMessage`
```python
{ 
    message_id: str,
    source_swarm: str, target_swarm: str,
    timestamp: str,
    payload: MAILRequest | MAILResponse | MAILBroadcast | MAILInterrupt,
    msg_type: Literal["request", "response", "broadcast", "interrupt"],
    auth_token: str | None,
    metadata: dict[str, Any] | None 
}
```
#### `MAILMessage`
```python
{
    id: str,
    timestamp: str,
    message: MAILRequest | MAILResponse | MAILBroadcast | MAILInterrupt,
    msg_type: Literal["request", "response", "broadcast", "interrupt", "broadcast_complete"] 
}
```
- **Helper utilities**: `parse_agent_address`, `format_agent_address`, `create_agent_address`, `create_user_address`, `create_system_address`, `build_body_xml`, `build_mail_xml`.

### Function reference

#### `mail.core.tools`
##### `pydantic_model_to_tool`
```python
  def pydantic_model_to_tool(
    model_cls,
    name=None,
    description=None,
    style="completions"
  ) -> dict[str, Any]
```
  - **Parameters**: Pydantic model class, optional tool name/description, OpenAI tool style.
  - **Returns**: Tool metadata dictionary compatible with OpenAI completions/responses APIs.
  - **Summary**: Convert a Pydantic model into an OpenAI tool schema.
##### `convert_call_to_mail_message`
```python
def convert_call_to_mail_message(
    call,
    sender,
    task_id
) -> MAILMessage
```
  - **Parameters**: `AgentToolCall`, sender agent name, task identifier.
  - **Returns**: MAIL envelope derived from the tool invocation.
  - **Summary**: Translate tool calls into MAIL protocol messages.
##### `create_request_tool`
```python
def create_request_tool(
    targets,
    enable_interswarm=False,
    style="completions"
) -> dict[str, Any]
```
  - **Summary**: Build a request-sending tool limited to a set of recipient agents (optional interswarm addressing).
##### `create_response_tool`
```python
def create_response_tool(
    targets,
    enable_interswarm=False,
    style="completions"
) -> dict[str, Any]
```
  - **Summary**: Build a response-sending tool mirroring `create_request_tool`.
##### `create_interrupt_tool`
```python
def create_interrupt_tool(
    targets,
    enable_interswarm=False,
    style="completions"
) -> dict[str, Any]
```
  - **Summary**: Build an interrupt tool for halting agent activity.
##### `create_interswarm_broadcast_tool`
```python
def create_interswarm_broadcast_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Summary**: Allow supervisors to broadcast messages across swarms.
##### `create_swarm_discovery_tool`
```python
def create_swarm_discovery_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Summary**: Emit a tool that registers discovery URLs for swarms.
##### `create_broadcast_tool`
```python
def create_broadcast_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Summary**: Broadcast to all agents within the local swarm.
##### `create_acknowledge_broadcast_tool`
```python
def create_acknowledge_broadcast_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Summary**: Store broadcasts in memory without responding.
##### `create_ignore_broadcast_tool` 
```python
def create_ignore_broadcast_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Summary**: Explicitly ignore a broadcast.
##### `create_task_complete_tool`
```python
def create_task_complete_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Summary**: Mark a task as finished and communicate the final answer.
##### `create_mail_tools`
```python
def create_mail_tools(
    targets, 
    enable_interswarm=False, 
    style="completions"
) -> list[dict[str, Any]]
```
  - **Summary**: Convenience helper combining request/response/broadcast acknowledgement tools.
##### `create_supervisor_tools`
```python
def create_supervisor_tools(
    targets, 
    can_complete_tasks=True, 
    enable_interswarm=False, 
    style="completions", 
    _debug_include_intraswarm=True
) -> list[dict[str, Any]]
```
  - **Summary**: Supervisor-focused tool bundle including interrupts, broadcasts, discovery, and task completion.

#### `mail.utils.auth`
- `login(api_key: str) -> Awaitable[str]`
  - **Summary**: Exchange an API key for a bearer token via the auth service.
- `get_token_info(token: str) -> Awaitable[dict[str, Any]]`
  - **Summary**: Resolve a token into `{ role, id, api_key }` metadata.
- `caller_is_admin(request)`, `caller_is_user(request)`, `caller_is_agent(request)`, `caller_is_admin_or_user(request) -> Awaitable[bool]`
  - **Summary**: FastAPI dependency helpers that enforce role-based access.
- `extract_token_info(request) -> Awaitable[dict[str, Any]]`
  - **Summary**: Pull token metadata from the incoming request headers.
- `generate_user_id(token_info) -> str`
  - **Summary**: Deterministically format a user identifier (`role_id`).
- `generate_agent_id(token_info) -> str`
  - **Summary**: Deterministically format an interswarm agent identifier (`swarm_id`).

#### `mail.utils.logger`
- `get_loggers() -> list[str]`
  - **Summary**: List currently registered Python loggers.
- `init_logger() -> None`
  - **Summary**: Configure Rich console logging plus rotating file output under `logs/`.

#### `mail.utils.parsing`
- `read_python_string(string: str) -> Any`
  - **Summary**: Import `module:attribute` strings at runtime (used by templates).
- `target_address_is_interswarm(address: str) -> bool`
  - **Summary**: Determine whether an address targets a remote swarm (`agent@swarm`).

#### `mail.utils.store`
- `get_langmem_store() -> AsyncIterator[Any]`
  - **Summary**: Async context manager yielding a LangMem memory store (Postgres when configured, otherwise in-memory).

### Example: programmatic swarm assembly

```python
import asyncio

from mail import MAILAgentTemplate, MAILSwarmTemplate
from mail.examples import weather_dummy  # Provides demo agent params and tools

# Build reusable agent templates from the bundled examples
supervisor = MAILAgentTemplate.from_example("supervisor", comm_targets=["weather"])
weather = MAILAgentTemplate.from_example("weather", comm_targets=["supervisor"])

# Assemble a swarm template that links the agents together
demo_template = MAILSwarmTemplate(
    name="demo-swarm",
    agents=[supervisor, weather],
    actions=[*supervisor.actions, *weather.actions],
    entrypoint="supervisor",
)

async def main() -> None:
    # Instantiate a concrete swarm runtime for a specific user
    swarm = demo_template.instantiate(instance_params={}, user_id="demo-user")
    # Post a message to the supervisor entrypoint and capture optional events
    response, events = await swarm.post_message(
        subject="Forecast check",
        body="What's the outlook for tomorrow in New York?",
        show_events=True,
    )
    # Emit the supervisor's final answer
    print(response["message"]["body"])
    # Always shut the runtime down to flush background tasks
    await swarm.shutdown()

asyncio.run(main())
```

This snippet constructs two agents from the bundled examples, wires them into a `MAILSwarmTemplate`, instantiates the swarm for a specific user, posts a request, and finally tears the runtime down.
