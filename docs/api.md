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
| GET | `/` | None (public) | `None` | `types.GetRootResponse { name, status, protocol_version, swarm: SwarmInfo, uptime }` | Returns MAIL service metadata and version string. `SwarmInfo` includes `name`, `version`, `description`, `entrypoint`, `keywords`, and `public`. |
| GET | `/status` | `Bearer` token with role `admin` or `user` | `None` | `types.GetStatusResponse { swarm, active_users, user_mail_ready, user_task_running }` | Reports persistent swarm readiness and whether the caller already has a running runtime |
| GET | `/whoami` | `Bearer` token with role `admin` or `user` | `None` | `types.GetWhoamiResponse { id, role }` | Returns the caller identifier and role associated with the provided token |
| POST | `/message` | `Bearer` token with role `admin` or `user` | `JSON { subject: str, body: str, msg_type?: str, entrypoint?: str, show_events?: bool, stream?: bool, task_id?: str, resume_from?: str, kwargs?: dict }` | `types.PostMessageResponse { response: str, events?: list[ServerSentEvent] }` (or `text/event-stream` when `stream: true`) | Queues or resumes a user-scoped task; supports breakpoint resumes via `resume_from="breakpoint_tool_call"` and extra kwargs |
| GET | `/tasks` | `Bearer` token with role `admin` or `user` | `None` | `dict[str, TaskRecord]` | Lists all tasks owned by the caller together with runtime metadata |
| GET | `/task` | `Bearer` token with role `admin` or `user` | `JSON { task_id: str }` | `TaskRecord` | Returns the full record for a single task, including SSE history and queue snapshot |
| GET | `/health` | None (public) | `None` | `types.GetHealthResponse { status, swarm_name, timestamp }` | Liveness signal used for interswarm discovery |
| POST | `/health` | `Bearer` token with role `admin` | `JSON { status: str }` | `types.GetHealthResponse { status, swarm_name, timestamp }` | Updates the health status reported to other swarms |
| GET | `/swarms` | None (public) | `None` | `types.GetSwarmsResponse { swarms: list[types.SwarmEndpointCleaned] }` | Lists *public* swarms known to the local registry. Returns cleaned endpoints (auth tokens hidden) with fields: `swarm_name`, `base_url`, `version`, `last_seen`, `is_active`, `latency`, `swarm_description`, `keywords`, `metadata`. |
| POST | `/swarms` | `Bearer` token with role `admin` | `JSON { name: str, base_url: str, auth_token?: str, metadata?: dict, volatile?: bool }` | `types.PostSwarmsResponse { status, swarm_name }` | Registers a remote swarm (persistent when `volatile` is `False`) |
| GET | `/swarms/dump` | `Bearer` token with role `admin` | `None` | `types.GetSwarmsDumpResponse { status, swarm_name }` | Logs the configured persistent swarm and returns acknowledgement |
| POST | `/interswarm/forward` | `Bearer` token with role `agent` | `JSON { message: MAILInterswarmMessage }` | `types.PostInterswarmForwardResponse { swarm, task_id, status, local_runner }` | Accepts a remote swarm's new-task payload and spawns/attaches a local runtime |
| POST | `/interswarm/back` | `Bearer` token with role `agent` | `JSON { message: MAILInterswarmMessage }` | `types.PostInterswarmBackResponse { swarm, task_id, status, local_runner }` | Injects a follow-up or completion payload from the remote swarm into the active local runtime |
| POST | `/interswarm/message` | `Bearer` token with role `admin` or `user` | `JSON { user_token: str, body: str, targets: list[str], subject?: str, msg_type?: Literal["request","broadcast"], task_id?: str, routing_info?: dict, stream?: bool, ignore_stream_pings?: bool }` | `types.PostInterswarmMessageResponse { response: MAILMessage, events?: list[ServerSentEvent] }` | Proxies a user/admin task to a remote swarm using the caller's runtime and interswarm router |
| POST | `/swarms/load` | `Bearer` token with role `admin` | `JSON { json: str }` (serialized swarm template) | `types.PostSwarmsLoadResponse { status, swarm_name }` | Replaces the persistent swarm template using a JSON document |
| POST | `/responses` | `Bearer` token with role `admin` or `user` (debug mode only) | `JSON { input: list[dict], tools: list[dict], instructions?: str, previous_response_id?: str, tool_choice?: str \| dict, parallel_tool_calls?: bool, kwargs?: dict }` | `openai.types.responses.Response` | OpenAI Responses-compatible bridge available when the server runs with `debug` enabled; not included in the public OpenAPI spec |

**TaskRecord** aligns with [`mail.core.tasks.MAILTask`](/src/mail/core/tasks.py):
- `task_id`, `task_owner`, `task_contributors`, `start_time`, `is_running`, `completed`, `remote_swarms` summarise runtime status
- `events` echoes the task's Server-Sent Event log (each entry is serialised with `event`, `id`, `retry`, `data`)
- `task_message_queue` contains any stashed downstream messages used when resuming paused work
`GET /task` expects a small JSON body with `task_id` even though it is a GET request—this keeps the signature consistent with other task-management helpers without exposing the identifier in query parameters.

### SSE streaming
- `POST /message` with `stream: true` yields a `text/event-stream`
- **Events** include periodic `ping` heartbeats and terminate with `task_complete` carrying the final serialized response
- When resuming a task from a breakpoint tool call, provide `resume_from="breakpoint_tool_call"` and include `breakpoint_tool_call_result` inside `kwargs`. Pass a JSON string, dict, or list that represents either a single tool response (`{"content": "..."}`) or a list of responses (`[{"call_id": "...", "content": "..."}]`) so the runtime can fan the outputs back to the corresponding breakpoint tool calls.
- `POST /interswarm/message` accepts the same customization flags as local messaging. Use `msg_type="request"` with a single-element `targets` list, or `msg_type="broadcast"` with one or more entries. Include `stream` / `ignore_stream_pings` to mirror local streaming; the server copies those hints into the interswarm `routing_info` it sends downstream.

### Debug mode & OpenAI compatibility
- Enabling server debug mode (`mail server --debug` or `[server].debug = true`) bootstraps a `SwarmOAIClient` alongside the FastAPI app so it can mirror OpenAI's `/responses` API.
- `POST /responses` expects the OpenAI-style `input`, `tools`, `instructions`, `previous_response_id`, and other optional fields. The caller is authenticated via the normal `Authorization: Bearer ...` header, which is used to hydrate or reuse the caller's MAIL runtime before piping the request into the OpenAI bridge.
- Responses conform to `openai.types.responses.Response`, letting you plug a MAIL swarm behind clients or SDKs that already speak the OpenAI Responses protocol. Because it is debug-only, the route is hidden from the generated OpenAPI document.
- Wrap it from code via `MAILClient.debug_post_responses(...)` or from the REPL using `mail client responses …` (see [client.md](/docs/client.md) and [cli.md](/docs/cli.md) for usage).

### Error handling
- FastAPI raises **standard HTTP errors** with a `detail` field
- The runtime emits **structured MAIL error responses** when routing or execution fails

### Notes
- The server keeps a persistent `MAILSwarmTemplate` catalogue and per-user `MAILSwarm` instances
- **Message schemas** are documented in [docs/message-format.md](/docs/message-format.md) and [spec/](/spec/SPEC.md)
- The repository ships an asynchronous helper described in [docs/client.md](/docs/client.md) that wraps these endpoints and handles bearer auth + SSE parsing
- **Task lifecycle**: Each `POST /message` participates in a long-lived task distinguished by `task_id`. Breakpoint-aware tools can pause a task; clients resume by reusing the same `task_id` with the `resume_from` contract described above. Both `resume_from="breakpoint_tool_call"` (supply tool output via `kwargs`) and `resume_from="user_response"` (send another user-authored message) are supported.

### MAILClient helper
- `MAILClient` (see [client.md](/docs/client.md)) mirrors every route above with ergonomic async methods
- Supports bearer tokens, custom timeouts, and optional externally managed `aiohttp.ClientSession`
- Provides `post_message_stream()` to yield `ServerSentEvent` objects without recreating SSE parsing logic
- Used by automated tests and demo scripts (`scripts/demo_client.py`) to validate client/server interoperability

## Python API

The Python surface is designed for embedding MAIL inside other applications, building custom swarms, or scripting tests. The primary exports live in [src/mail/\_\_init\_\_.py](/src/mail/__init__.py) and re-export key classes from `mail.api` and `mail.core`.

### Imports and modules
- To obtain **high-level builder classes**:
  ```python 
  from mail import (
    MAILAgent, 
    MAILAgentTemplate, 
    MAILAction, 
    MAILSwarm, 
    MAILSwarmTemplate
  )
  ``` 
- To obtain **protocol types**:
  ```python
  from mail import (
      MAILMessage,
      MAILRequest,
      MAILResponse,
      MAILBroadcast,
      MAILInterrupt,
      AgentToolCall,
  )
  ```
- To obtain **network helpers** for interswarm support:
  ```python
  from mail.net import SwarmRegistry, InterswarmRouter
  ```
- To work directly with the lower-level runtime primitives:
  ```python
  from mail.core import AgentCore, ActionCore
  ```
- `mail.utils` bundles token helpers, logging utilities, dynamic function loading via `read_python_string`, and interswarm address parsing
- `mail.swarms_json.utils` provides lightweight helpers for loading and validating `swarms.json` content before instantiating templates

### Class reference

#### `MAILAction` (`mail.api`)
- **Summary**: Describes an action/tool exposed by an agent; wraps a callable with metadata for OpenAI tools.
- **Constructor parameters**: `name: str`, `description: str`, `parameters: dict[str, Any]` (JSONSchema-like), `function: str | ActionFunction` (import string or callable).
- **Key methods**:
  - `from_pydantic_model(model, function_str, name?, description?) -> MAILAction`: build from a Pydantic model definition.
  - `from_swarm_json(json_str) -> MAILAction`: rebuild from persisted `swarms.json` entries.
   - `to_tool_dict(style="responses"|"completions") -> dict[str, Any]`: emit an OpenAI-compatible tool declaration.
   - `to_pydantic_model(for_tools: bool = False) -> type[BaseModel]`: create a Pydantic model for validation or schema reuse.
   - `_validate() -> None` and `_build_action_function(function) -> ActionFunction`: internal guards and loader utilities.

#### `action` decorator (`mail.api`)
- **Summary**: Decorator that turns a Python callable into a `MAILAction`, wiring up schema validation and tool metadata automatically.
- **Parameters**:
  - `name: str | None` – optional override; defaults to the function name.
  - `description: str | None` – required unless supplied via docstring.
  - `model: type[BaseModel] | None` – payload schema; inferred from the first argument annotation when it is a `BaseModel` subclass.
  - `parameters: dict[str, Any] | None` – manual JSON schema (mutually exclusive with `model`).
  - `style: Literal["responses", "completions"]` – schema flavor passed to `pydantic_model_to_tool` (default `"responses"`).
- **Usage**:
  ```python
  from pydantic import BaseModel
  from mail import action

  class WeatherRequest(BaseModel):
      city: str

  @action(description="Return weather information for the requested city.")
  async def get_weather(payload: WeatherRequest) -> str:
      forecast = lookup_forecast(payload.city)
      return forecast.json()

  # get_weather is now a MAILAction ready to install on an agent:
  weather_action = get_weather
  ```

#### `MAILAgent` (`mail.api`)
- **Summary**: Concrete runtime agent produced by an agent factory and associated actions.
- **Constructor parameters**: `name: str`, `factory: str | Callable`, `actions: list[MAILAction]`, `function: AgentFunction`, `comm_targets: list[str]`, `agent_params: dict[str, Any]`, `enable_entrypoint: bool = False`, `enable_interswarm: bool = False`, `can_complete_tasks: bool = False`, `tool_format: Literal["completions", "responses"] = "responses"`, `exclude_tools: list[str] | None = None`.
- **Key methods**:
  - `__call__(messages, tool_choice="required") -> Awaitable[tuple[str | None, list[AgentToolCall]]]`: execute the agent implementation.
  - `_to_template(names: list[str]) -> MAILAgentTemplate`: internal helper that trims targets for sub-swarms.
  - `_validate() -> None`: internal guard ensuring agent metadata is coherent.
- Factories may be supplied as dotted import strings (resolved via `read_python_string`) or as preloaded callables.

#### `MAILAgentTemplate` (`mail.api`)
- **Summary**: Declarative agent description used for persistence, cloning, and factory instantiation.
- **Constructor parameters**: `name: str`, `factory: str | Callable`, `comm_targets: list[str]`, `actions: list[MAILAction]`, `agent_params: dict[str, Any]`, `enable_entrypoint: bool = False`, `enable_interswarm: bool = False`, `can_complete_tasks: bool = False`, `tool_format: Literal["completions", "responses"] = "responses"`, `exclude_tools: list[str] | None = None`.
- **Key methods**:
  - `instantiate(instance_params: dict[str, Any]) -> MAILAgent`: load the factory and produce a concrete `MAILAgent`.
  - `from_swarm_json(json_str, actions_by_name: dict[str, MAILAction] | None = None) -> MAILAgentTemplate`: rebuild from `swarms.json` entries, optionally supplying pre-built actions to resolve `actions` references efficiently.
  - `from_example(name, comm_targets) -> MAILAgentTemplate`: load bundled examples (`supervisor`, `weather`, `math`, `consultant`, `analyst`).
  - `_top_level_params() -> dict[str, Any]` and `_validate() -> None`: internal helpers used during instantiation and validation.
- Accepts either dotted import strings or callables for `factory`, enabling JSON-driven and dynamic runtime construction alike.
- Recursively resolves `python::module:object` and `url::https://...` string prefixes in `agent_params` (and nested structures) so templates can reference code exports or remote JSON payloads without manual preprocessing.

#### `MAILSwarm` (`mail.api`)
- **Summary**: Runtime container that owns instantiated agents/actions and embeds a `MAILRuntime`.
- **Constructor parameters**: `name: str`, `version: str`, `agents: list[MAILAgent]`, `actions: list[MAILAction]`, `entrypoint: str`, `user_id: str = "default"`, `user_role: Literal["admin","agent","user"] = "user"`, `swarm_registry: SwarmRegistry | None = None`, `enable_interswarm: bool = False`, `breakpoint_tools: list[str] = []`, `exclude_tools: list[str] = []`, `task_message_limit: int | None = None`, `description: str = ""`, `keywords: list[str] = []`, `enable_db_agent_histories: bool = False`.
- **Key methods**:
  - `post_message(...)`, `post_message_stream(...)`, `post_message_and_run(...)`: enqueue user requests (optionally streaming or running to completion).
  - `submit_message(...)`, `submit_message_stream(...)`: submit fully-formed `MAILMessage` envelopes.
  - `run_continuous(action_override: ActionOverrideFunction | None = None) -> Awaitable[None]`: long-running loop for user sessions.
  - `shutdown()`, `start_interswarm()`, `stop_interswarm()`, `is_interswarm_running()`: lifecycle and interswarm controls.
  - `handle_interswarm_response(response_message) -> Awaitable[None]`: process responses from remote swarms.
  - `route_interswarm_message(message) -> Awaitable[MAILMessage]`: send outbound interswarm traffic via the router.
  - `get_pending_requests() -> dict[str, asyncio.Future[MAILMessage]]`: inspect outstanding requests per task.
  - `update_from_adjacency_matrix(adj: list[list[int]]) -> None`: overwrite agent communication targets using an adjacency matrix.
  - `get_subswarm(names, name_suffix, entrypoint?) -> MAILSwarmTemplate`: derive a sub-template focused on a subset of agents.
  - `build_message(subject, body, targets, sender_type?, type?) -> MAILMessage`: utility for crafting MAIL envelopes.

#### `MAILSwarmTemplate` (`mail.api`)
- **Summary**: Immutable swarm blueprint comprised of `MAILAgentTemplate`s and shared actions.
- **Notes**: Inline definitions from `actions` may be combined with `action_imports` that resolve to decorated `MAILAction` objects (e.g., from `mail.stdlib`).
- **Constructor parameters**: `name: str`, `version: str`, `agents: list[MAILAgentTemplate]`, `actions: list[MAILAction]`, `entrypoint: str`, `enable_interswarm: bool = False`, `breakpoint_tools: list[str] = []`, `exclude_tools: list[str] = []`, `task_message_limit: int | None = None`, `description: str = ""`, `keywords: list[str] = []`, `public: bool = False`, `enable_db_agent_histories: bool = False`.
- **Key methods**:
  - `instantiate(instance_params, user_id?, user_role?, base_url?, registry_file?) -> MAILSwarm`: produce a runtime swarm (creates `SwarmRegistry` when interswarm is enabled).
  - `get_subswarm(names, name_suffix, entrypoint?) -> MAILSwarmTemplate`: filter agents into a smaller template while preserving supervisors and entrypoints.
  - `update_from_adjacency_matrix(adj: list[list[int]]) -> None`: sync template wiring back to `comm_targets` for each agent.
  - `from_swarm_json(json_str) -> MAILSwarmTemplate` / `from_swarm_json_file(swarm_name, json_filepath?) -> MAILSwarmTemplate`: rebuild from persisted JSON.
  - `_build_adjacency_matrix() -> tuple[list[list[int]], list[str]]`, `_validate() -> None`: internal helpers.

#### `AgentToolCall` (`mail.core.tools`)
- **Summary**: Pydantic model capturing the outcome of an OpenAI tool invocation.
- **Fields**: `tool_name: str`, `tool_args: dict[str, Any]`, `tool_call_id: str`, `completion: dict[str, Any]`, `responses: list[dict[str, Any]]`, `reasoning: list[str] | None`, `preamble: str | None`.
- **Key methods**:
  - `create_response_msg(content: str) -> dict[str, str]`: format a response payload for completions or responses API.
  - `model_validator` (after-init) enforces that either `completion` or `responses` is populated.

#### `MAILRuntime` (`mail.core.runtime`)
- **Summary**: Asynchronous runtime that owns the internal message queue, tool execution, and optional interswarm router.
- **Constructor parameters**: `agents: dict[str, AgentCore]`, `actions: dict[str, ActionCore]`, `user_id: str`, `user_role: Literal["admin","agent","user"]`, `swarm_name: str = "example"`, `entrypoint: str = "supervisor"`, `swarm_registry: SwarmRegistry | None = None`, `enable_interswarm: bool = False`, `breakpoint_tools: list[str] | None = None`, `exclude_tools: list[str] | None = None`, `enable_db_agent_histories: bool = False`.
- Pass the lower-level `AgentCore` / `ActionCore` objects (for example via `MAILAgent.to_core()` and `MAILAction.to_core()`) when instantiating the runtime directly.
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
- **Constructor parameters**: `local_swarm_name: str`, `local_base_url: str`, `persistence_file: str | None = None`, `local_swarm_description: str = ""`, `local_swarm_keywords: list[str] | None = None`, `local_swarm_public: bool = False`.
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
    address_type: Literal["admin", "agent", "user", "system"], 
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
    task_owner: str,
    task_contributors: list[str],
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
  - **Parameters**: `model_cls: type[BaseModel]` – Pydantic model describing the tool payload; `name: str | None` – optional override for the tool name; `description: str | None` – supplemental natural language description; `style: Literal["completions", "responses"]` – which OpenAI API surface the schema will target.
  - **Returns**: `dict[str, Any]` – Tool metadata in the shape expected by the chosen OpenAI API.
  - **Summary**: Wraps Pydantic models with OpenAI metadata so MAIL agents can advertise structured tool calls across both the Chat Completions and Responses APIs.
##### `convert_call_to_mail_message`
```python
def convert_call_to_mail_message(
    call,
    sender,
    task_id
) -> MAILMessage
```
  - **Parameters**: `call: AgentToolCall` – serialized OpenAI tool invocation captured from the LLM; `sender: str` – MAIL agent name that issued the tool call; `task_id: str` – runtime task identifier tying the message to a conversation loop.
  - **Returns**: `MAILMessage` – Fully populated MAIL envelope ready for routing (request, response, broadcast, interrupt, or completion broadcast).
  - **Summary**: Normalizes OpenAI tool executions into canonical MAIL messages, setting message IDs, timestamps, and typed payloads so downstream routers can deliver them without additional parsing.
##### `create_request_tool`
```python
def create_request_tool(
    targets,
    enable_interswarm=False,
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `targets: list[str]` – approved in-swarm recipients for outgoing requests; `enable_interswarm: bool` – toggles free-form `agent@swarm` addressing; `style: Literal["completions", "responses"]` – OpenAI API surface to tailor schema for.
  - **Returns**: `dict[str, Any]` – OpenAI tool definition whose schema enforces MAIL request fields.
  - **Summary**: Produces a constrained `send_request` tool that lets agents originate MAIL requests while guarding the recipient list and optionally annotating interswarm routing hints.
##### `create_response_tool`
```python
def create_response_tool(
    targets,
    enable_interswarm=False,
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `targets: list[str]` – eligible response recipients; `enable_interswarm: bool` – permits remote swarm addressing when true; `style: Literal["completions", "responses"]` – selects schema layout for the target OpenAI API.
  - **Returns**: `dict[str, Any]` – OpenAI tool description for the `send_response` helper.
  - **Summary**: Mirrors `create_request_tool` but directs the payload through the MAIL response channel so agents can close loops or send follow-ups with correct metadata.
##### `create_interrupt_tool`
```python
def create_interrupt_tool(
    targets,
    enable_interswarm=False,
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `targets: list[str]` – agents whose execution can be interrupted; `enable_interswarm: bool` – expands targeting to `agent@swarm`; `style: Literal["completions", "responses"]` – determines tool schema format.
  - **Returns**: `dict[str, Any]` – OpenAI definition for the `send_interrupt` tool.
  - **Summary**: Enables supervisor-style interventions by emitting MAIL interrupt envelopes that pause or redirect downstream agents, preserving target validation rules.
##### `create_interswarm_broadcast_tool`
```python
def create_interswarm_broadcast_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `style: Literal["completions", "responses"]` – OpenAI API variant that should consume the tool description.
  - **Returns**: `dict[str, Any]` – Tool metadata for `send_interswarm_broadcast`.
  - **Summary**: Provides supervisors with a broadcast primitive that targets multiple remote swarms, including optional filtering of destination swarm names.
##### `create_swarm_discovery_tool`
```python
def create_swarm_discovery_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `style: Literal["completions", "responses"]` – dictates OpenAI schema flavor.
  - **Returns**: `dict[str, Any]` – Tool definition for `discover_swarms`.
  - **Summary**: Lets supervisors push discovery endpoint URLs into the registry so the runtime can crawl and register additional swarms on demand.
##### `create_broadcast_tool`
```python
def create_broadcast_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `style: Literal["completions", "responses"]` – OpenAI API compatibility toggle.
  - **Returns**: `dict[str, Any]` – Tool metadata for `send_broadcast`.
  - **Summary**: Issues swarm-wide broadcasts inside the local runtime, allowing supervisors to disseminate guidance or status simultaneously to every agent.
##### `create_acknowledge_broadcast_tool`
```python
def create_acknowledge_broadcast_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `style: Literal["completions", "responses"]` – chooses schema variant for OpenAI tools.
  - **Returns**: `dict[str, Any]` – Tool payload describing `acknowledge_broadcast`.
  - **Summary**: Gives agents a non-disruptive acknowledgement path that stores incoming broadcasts in local memory without generating MAIL traffic.
##### `create_ignore_broadcast_tool` 
```python
def create_ignore_broadcast_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `style: Literal["completions", "responses"]` – determines returned schema format.
  - **Returns**: `dict[str, Any]` – Tool metadata for `ignore_broadcast`.
  - **Summary**: Allows agents to discard a broadcast intentionally, optionally recording an internal reason while ensuring no acknowledgement is emitted.
##### `create_await_message_tool`
```python
def create_await_message_tool(
    style="completions"
) -> dict[str, Any]
```
- **Parameters**: `style: Literal["completions", "responses"]` – specifies the OpenAI schema flavor to emit.
- **Returns**: `dict[str, Any]` – Tool description for `await_message` with an optional `reason` field.
- **Summary**: Gives agents a MAIL-native way to yield their turn once they have no additional output; the optional reason is surfaced in runtime events and tool-call history for observability.
##### `create_help_tool`
```python
def create_help_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `style: Literal["completions", "responses"]` – determines the OpenAI schema format returned.
  - **Returns**: `dict[str, Any]` – Tool specification for `help` with toggles for summary, identity, per-tool guidance, and full protocol output.
  - **Summary**: Produces the diagnostic helper that agents can call to learn about their identity, available MAIL tools, and optionally the entire protocol specification; the runtime relays the generated content back via a system broadcast.
##### `create_task_complete_tool`
```python
def create_task_complete_tool(
    style="completions"
) -> dict[str, Any]
```
  - **Parameters**: `style: Literal["completions", "responses"]` – aligns the schema with the OpenAI API being used.
  - **Returns**: `dict[str, Any]` – Tool specification for `task_complete`.
  - **Summary**: Produces the termination tool supervisors use to broadcast the final user-facing answer and signal the runtime that the task loop can close.
##### `create_mail_tools`
```python
def create_mail_tools(
    targets, 
    enable_interswarm=False, 
    style="completions"
) -> list[dict[str, Any]]
```
  - **Parameters**: `targets: list[str]` – baseline intra-swarm recipients; `enable_interswarm: bool` – toggles remote routing support; `style: Literal["completions", "responses"]` – OpenAI schema variant shared by all generated tools.
  - **Returns**: `list[dict[str, Any]]` – Bundled request, response, acknowledgement, ignore, await, and help tools configured with the provided options.
  - **Summary**: Supplies a ready-to-install toolkit for standard agents so they can message peers, manage broadcasts, request runtime help, or explicitly wait for new mail without bespoke configuration.
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
  - **Parameters**: `targets: list[str]` – intra-swarm agents reachable by the supervisor; `can_complete_tasks: bool` – gates inclusion of the task completion tool; `enable_interswarm: bool` – toggles remote messaging and discovery helpers; `style: Literal["completions", "responses"]` – controls schema flavor; `_debug_include_intraswarm: bool` – retains intra-swarm tools when debugging or running evaluations.
  - **Returns**: `list[dict[str, Any]]` – Curated tool set composed of interrupts, broadcasts, discovery, and optional completion helpers.
  - **Summary**: Tailors the MAIL control surface for supervisory agents, combining escalation, coordination, discovery, and shutdown capabilities into a single toolkit.

#### `mail.utils.auth`
##### `login`
```python
def login(
    api_key: str
) -> Awaitable[str]
```
  - **Parameters**: `api_key: str` – credential provided by the operator or registry.
  - **Returns**: `Awaitable[str]` – coroutine resolving to a bearer token when the auth service accepts the key.
  - **Summary**: Performs the remote API key exchange, logs successful authentications, and yields the token MAIL uses for subsequent secured calls.
##### `get_token_info`
```python
def get_token_info(
    token: str
) -> Awaitable[dict[str, Any]]
```
  - **Parameters**: `token: str` – bearer token previously issued by the auth service.
  - **Returns**: `Awaitable[dict[str, Any]]` – coroutine yielding the decoded token payload (role, id, api key reference, etc.).
  - **Summary**: Queries the token introspection endpoint to materialize role metadata used by all downstream authorization checks.
##### `caller_is_admin`
```python
def caller_is_admin(
    request
) -> Awaitable[bool]
```
  - **Parameters**: `request: fastapi.Request` – inbound HTTP request carrying the bearer token header.
  - **Returns**: `Awaitable[bool]` – coroutine resolving to `True` when the token role is `admin`, otherwise raises `HTTPException`.
  - **Summary**: FastAPI dependency that gates endpoints to administrators by validating the caller’s token role against the auth service.
##### `caller_is_user`
```python
def caller_is_user(
    request
) -> Awaitable[bool]
```
  - **Parameters**: `request: fastapi.Request` – HTTP request containing an Authorization header.
  - **Returns**: `Awaitable[bool]` – coroutine that resolves to `True` when the token role is `user` (otherwise raises `HTTPException`).
  - **Summary**: Dependable guard that restricts endpoints to end users, reusing the shared role-checking helper.
##### `caller_is_agent`
```python
def caller_is_agent(
    request
) -> Awaitable[bool]
```
  - **Parameters**: `request: fastapi.Request` – bearer-authenticated HTTP request.
  - **Returns**: `Awaitable[bool]` – coroutine returning `True` if the caller’s role is `agent`, otherwise raising `HTTPException`.
  - **Summary**: Dependency enforcing that only MAIL agents (typically other swarms) can access agent-scoped endpoints.
##### `caller_is_admin_or_user`
```python
def caller_is_admin_or_user(
    request
) -> Awaitable[bool]
```
  - **Parameters**: `request: fastapi.Request` – inbound request from which the method extracts and validates the bearer token.
  - **Returns**: `Awaitable[bool]` – coroutine that resolves to `True` for `admin` or `user` callers, raising `HTTPException` for all others.
  - **Summary**: Combined guard that accepts either administrative or end-user tokens while protecting against malformed or mis-scoped Authorization headers.
##### `extract_token_info`
```python
def extract_token_info(
    request
) -> Awaitable[dict[str, Any]]
```
  - **Parameters**: `request: fastapi.Request` – request object containing bearer token details.
  - **Returns**: `Awaitable[dict[str, Any]]` – coroutine yielding the token metadata dictionary retrieved from the auth service.
  - **Summary**: Utility dependency that unwraps the Authorization header, normalizes the bearer token, and returns the decoded payload for downstream handlers.
##### `generate_user_id`
```python
def generate_user_id(
    token_info
) -> str
```
  - **Parameters**: `token_info: dict[str, Any]` – decoded token payload from the auth service.
  - **Returns**: `str` – stable user identifier combining the caller role and id.
  - **Summary**: Formats the composite user identifier MAIL uses to partition runtimes and per-user state.
##### `generate_agent_id`
```python
def generate_agent_id(
    token_info
) -> str
```
  - **Parameters**: `token_info: dict[str, Any]` – token payload describing the remote agent.
  - **Returns**: `str` – prefixed identifier (`swarm_<id>`) used for interswarm routing and persistence keys.
  - **Summary**: Produces the canonical agent identifier expected by registry and routing components.

#### `mail.utils.logger`
##### `get_loggers`
```python
def get_loggers() -> list[str]
```
  - **Returns**: `list[str]` – names of loggers tracked by the root logging manager.
  - **Summary**: Exposes the logging subsystem’s registry so callers can audit or reconfigure loggers programmatically.
##### `init_logger`
```python
def init_logger() -> None
```
  - **Returns**: `None`.
  - **Summary**: Builds MAIL’s logging pipeline by wiring Rich console output, daily rotating file handlers, and sanitizing third-party logger configurations before runtime startup.

#### `mail.utils.parsing`
##### `read_python_string`
```python
def read_python_string(
    string: str
) -> Any
```
  - **Parameters**: `string: str` – import target in `module:attribute` format.
  - **Returns**: `Any` – referenced attribute imported dynamically from the specified module.
  - **Summary**: Supports template-driven configuration by resolving dotted module references into live Python objects.
##### `target_address_is_interswarm`
```python
def target_address_is_interswarm(
    address: str
) -> bool
```
  - **Parameters**: `address: str` – MAIL address such as `agent` or `agent@swarm`.
  - **Returns**: `bool` – `True` when the address encodes a remote swarm component, otherwise `False`.
  - **Summary**: Uses the core address parser to distinguish local recipients from interswarm destinations for routing decisions.

#### `mail.utils.store`
##### `get_langmem_store`
```python
def get_langmem_store() -> AsyncIterator[Any]
```
  - **Returns**: `AsyncIterator[Any]` – async context manager that yields either a Postgres-backed LangMem store or an in-memory fallback.
  - **Summary**: Centralizes memory-store provisioning, negotiating Postgres connectivity, schema options, and in-memory fallbacks while presenting a consistent async context manager interface.

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
