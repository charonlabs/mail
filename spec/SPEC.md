# Multi-Agent Interface Layer (MAIL) — Specification

- **Version**: 1.2-pre1
- **Date**: October 24, 2025
- **Status**: Open to feedback
- **Scope**: Defines the data model, addressing, routing semantics, runtime, and REST transport for interoperable communication among autonomous agents within and across swarms.
- **Authors**: Addison Kline (GitHub: [@addisonkline](https://github.com/addisonkline)), Will Hahn (GitHub: [@wsfhahn](https://github.com/wsfhahn)), Ryan Heaton (GitHub: [@rheaton64](https://github.com/rheaton64)), Jacob Hahn (GitHub: [@jacobtohahn](https://github.com/jacobtohahn))

## Normative References

- **Core schema**: [spec/MAIL-core.schema.json](/spec/MAIL-core.schema.json) (JSON Schema[^jsonschema-core][^jsonschema-validation])
- **Interswarm schema**: [spec/MAIL-interswarm.schema.json](/spec/MAIL-interswarm.schema.json) (JSON Schema[^jsonschema-core][^jsonschema-validation])
- **REST API**: [spec/openapi.yaml](/spec/openapi.yaml) (OpenAPI 3.1[^openapi])

## Terminology

- **Action**: An agent tool call that is not defined within MAIL.
- **Admin**: A user with extended privileges inside a given MAIL HTTP(S)[^rfc9110] server.
- **Agent**: An autonomous process participating in MAIL.
- **Entrypoint**: An agent capable of receiving MAIL messages directly from a user.
- **Interswarm**: Communication between agents in different swarms via HTTP(S).
- **MAIL Instance**: Runtime engine handling message queues,  agent interactions, and action calls for a user or swarm.
- **Supervisor**: An agent capable of completing a task.
- **Swarm**: A named deployment domain hosting a set of agents and providing a runtime for actions.
- **Task**: A user-defined query sent to a swarm entrypoint that agents complete through collaboration over MAIL.
- **User**: A human or external client initiating a task.

## Requirements Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119[^rfc2119] and RFC 8174[^rfc8174] when, and only when, they appear in all capitals.

## Conformance

- Producers MUST emit messages conforming to the JSON Schemas[^jsonschema-core][^jsonschema-validation] referenced above.
- Consumers MUST validate at least the presence and type of `msg_type`, `id`, `timestamp`, and the required fields for the bound payload type.
- Implementations of HTTP transport MUST conform to [spec/openapi.yaml](/spec/openapi.yaml) (OpenAPI 3.1[^openapi]).
- Interswarm implementations MUST accept both request and response wrappers and deliver payloads to local MAIL processing.

## Data Model

All types are defined in [spec/MAIL-core.schema.json](/spec/MAIL-core.schema.json) unless noted.

### `MAILAddress`

- **Fields**: `address_type` (enum: `agent|admin|user|system`), `address` (string).
- No `additionalProperties`.

### `MAILRequest`

- **Required**: `task_id` (uuid[^rfc4122]), `request_id` (uuid), `sender` (MAILAddress), `recipient` (MAILAddress), `subject` (string), `body` (string).
- **Optional**: `sender_swarm` (string), `recipient_swarm` (string), `routing_info` (object).
- No `additionalProperties`.

### `MAILResponse`

- **Required**: `task_id` (uuid), `request_id` (string), `sender`, `recipient`, `subject`, `body`.
- **Optional**: `sender_swarm`, `recipient_swarm`, `routing_info`.
- No `additionalProperties`.

### `MAILBroadcast`

- **Required**: `task_id` (uuid), `broadcast_id` (uuid), `sender`, `recipients` (array of `MAILAddress`, minItems=1), `subject`, `body`.
- **Optional**: `sender_swarm`, `recipient_swarms` (array of string), `routing_info`.
- No `additionalProperties`.

### `MAILInterrupt`

- **Required**: `task_id` (uuid), `interrupt_id` (uuid), `sender`, `recipients` (array of MAILAddress, minItems=1), `subject`, `body`.
- **Optional**: `sender_swarm`, `recipient_swarms`, `routing_info`.
- No `additionalProperties`.

### `MAILMessage`

- **Required**: `id` (uuid), `timestamp` (date-time[^rfc3339]), `message` (object), `msg_type` (enum: `request|response|broadcast|interrupt|broadcast_complete`).
- **Conditional binding**:
  - `msg_type=request` &rarr; `message` MUST be `MAILRequest`
  - `msg_type=response` &rarr; `message` MUST be `MAILResponse`
  - `msg_type=broadcast` &rarr; `message` MUST be `MAILBroadcast`
  - `msg_type=interrupt` &rarr; `message` MUST be `MAILInterrupt`
  - `msg_type=broadcast_complete` &rarr; `message` MUST be `MAILBroadcast`

### `MAILInterswarmMessage` ([spec/MAIL-interswarm.schema.json](/spec/MAIL-interswarm.schema.json))

- **Required**: `message_id` (string), `source_swarm` (string), `target_swarm` (string), `timestamp` (date-time), `payload` (object), `msg_type` (enum: `request|response|broadcast|interrupt`), `task_owner` (string), `task_contributors` (array).
- **Optional**: `auth_token` (string), `metadata` (object).
- Payload binding mirrors `MAILMessage` (payload is a core MAIL payload, not the outer wrapper).

## Addressing

- **Local address**: `name`
- **Remote (interswarm) address**: `name@swarm`
  
### Type `admin`

- Reserved for system administrators of a given MAIL swarm.
- Field `address` MUST be set to a unique identifier for each administrator.
- Field `address` MAY be a traditional username if those are fully unique; the reference implementation uses randomly-generated UUIDs for consistency.

### Type `agent`

- Reserved for autonomous agents participating in MAIL.
- Field `address` is used to identify agents; values of `address` MUST be unique within a swarm.
- Field `address` MAY follow interswarm schema.

### Type `system`

- Reserved for the swarm instance (runtime and router).
- Field `address` MUST be set to the swarm name.

### Type `user`

- Reserved for end-users of a given MAIL swarm.
- Field `address` MUST be set to a unique identifier for each user.
- Field `address` MAY be a traditional username if those are fully unique; the reference implementation uses randomly-generated UUIDs for consistency.

## Message Semantics

### Priority and Ordering

- **Tier 1 (highest)**: `*` from `system`
- **Tier 2**: `*` from `admin|user`
- **Tier 3**: `interrupt` from `agent`
- **Tier 4**: `broadcast` from `agent`
- **Tier 5 (lowest)**: `request|response` from `agent`
- Ties are ordered by `timestamp` (FIFO per priority class).

### Recipients

- **Single-recipient messages** use `recipient` (`MAILRequest`/`MAILResponse`).
- **Multi-recipient messages** use `recipients` (`MAILBroadcast`/`MAILInterrupt`).
- Special recipient `agent: all` indicates broadcast to all local agents. Therefore, every agent MUST NOT have `address=all`.

### Body Encoding

- `body` is free-form string. Systems MAY include structured content (e.g., XML snippets) for prompt formatting; no XML semantics are mandated by this spec.

## Tasks

- A MAIL **task** is identified by `task_id`.
- The task **completes** when a `broadcast_complete` for the corresponding `task_id` is produced by a supervisor in the swarm that initiated it.
- Systems using `submit_and_wait` MUST resolve awaiting futures only when `broadcast_complete` for that `task_id` is observed.
- Instances MUST store agent communication histories scoped by `task_id`.
- A given task MAY be referenced in a future request from the calling user, even after `task_complete`. Like new tasks, resumed tasks MUST resolve only on `task_complete`.

### Interswarm

- A given swarm MAY collaborate with remote swarms on a task.
- If a remote swarm gets messaged for a task with `task_id` *A*, it MUST use `task_id` *A* in its corresponding task process.
- Interswarm messages MUST include a field `task_owner`, containing the name of the instance where the task was created (in the format `role:id@swarm_name`).
- Interswarm messages MUST include a field `task_contributors`, containing the names of all instances that have processed this task. This list MUST include the `task_owner`.
- If a remote swarm calls `task_complete`, the finish message MUST be returned to the swarm instance that called it.
- When the `task_owner` instance calls `task_complete`, the remote swarms that contributed MUST be notified.

## Routing Semantics

- Implementers SHOULD impose limits on the agents reachable by any given agent.
  - The reference implementation requires a field `comm_targets: list[str]` for every agent, which serves this purpose.

### Local Routing

- If no swarm qualifier is present, or the qualifier matches the local swarm, the message MUST be delivered to local agent(s) by name.
- Unknown local agents SHOULD be logged and ignored.

### Interswarm Routing

- If a swarm qualifier is present (i.e., one or more addresses follow the format `agent-name@swarm-name`), the message MUST be delivered to the corresponding agent(s) by name. 
- If a remote agent does not exist or is otherwise unreachable, the sending agent MUST be notified.

## Runtime Model

- A **MAIL Instance**:
  - Maintains per-task message histories for context.
  - Executes agent tool calls, which may or may not be native to MAIL.
  - Tracks pending requests keyed by `task_id`; resolves only on `broadcast_complete`.
  - Supports continuous operation and graceful shutdown (waits for active tasks to finish).
- **MAIL Tools**:
  - See the [MAIL Tools](#mail-tools) section below.
- **Actions (Third Party Tools)**: 
  - Non-MAIL domain actions SHOULD emit action result broadcasts to inform interested agents.
- **Concurrency**:
  - Implementations SHOULD process asynchronously while preserving priority ordering semantics.

## MAIL Tools

### `send_request`

- Create a `MAILMessage` with `msg_type=request` from the given input and send to the specified recipient.
- **Required Parameters**: `target` (string), `subject` (string), `body` (string)
- **Returns**: None mandated by this spec.

### `send_response`

- Create a `MAILMessage` with `msg_type=response` from the given input and send it to the specified recipient.
- **Required Parameters**: `target` (string), `subject` (string), `body` (string)
- **Returns**: None mandated by this spec.

### `send_interrupt`

- Create a `MAILMessage` with `msg_type=interrupt` from the given input and send it to the specified recipient.
- **Required Parameters**: `target` (string), `subject` (string), `body` (string)
- **Returns**: None mandated by this spec.

### `send_broadcast`

- Create a `MAILMessage` with `msg_type=broadcast` and send it to `agent: all`.
- **Required Parameters**: `subject` (string), `body` (string)
- **Returns**: None mandated by this spec.

### `task_complete`

- Create a `MAILMessage` with `msg_type=broadcast_complete` and send it to `agent: all`.
- **Required Parameters**: `finish_message` (string)
- **Returns**: None mandated by this spec.

### `acknowledge_broadcast`

- Store a broadcast in agent memory without sending a response message.
- **Optional Parameters**: `note` (string)
- **Returns**: None mandated by this spec.

### `ignore_broadcast`

- Do not respond to a broadcast or store it in agent memory.
- **Optional Parameters**: `reason` (string)
- **Returns**: None mandated by this spec.

### `await_message`

- Indicate that the agent is finished with its current turn and should be scheduled again once a new MAIL message arrives.
- **Optional Parameters**: `reason` (string)
- **Returns**: None mandated by this spec.

## REST Transport

**Authoritative contract**: [spec/openapi.yaml](/spec/openapi.yaml) (OpenAPI 3.1[^openapi]).

### Security

- HTTP Bearer[^rfc6750] authentication.
- **Roles**:
  - `agent`: MAY call `/interswarm/forward`, `/interswarm/back`.
  - `user`: MAY call `/status`, `/whoami`, `/message`, `/swarms`, `/interswarm/message`.
  - `admin`: inherits `user` access and MAY additionally call `/swarms` (POST), `/swarms/dump`, `/swarms/load`.

### Endpoints

- **`GET /`**: Server metadata. Returns `{ name, version, swarm, status, uptime }`.
- **`GET /health`**: Health probe for interswarm peers. Returns `{ status, swarm_name, timestamp }`.
- **`GET /status`** (`user|admin`): Server status, including swarm and user-instance indicators.
- **`GET /whoami`** (`user|admin`): Returns `{ username, role }` derived from the presented token. Useful for clients to confirm identity/role assignments.
- **`POST /message`** (`user|admin`): Body `{ body: string, subject?: string, task_id?: string, entrypoint?: string, show_events?: boolean, stream?: boolean, resume_from?: user_response|breakpoint_tool_call, kwargs?: object }`. Creates a MAIL request to the swarm's default entrypoint (or user-specified `entrypoint`) and returns the final `response.body` when `broadcast_complete` resolves. When `stream=true`, the server responds with `text/event-stream` SSE events until completion.
- **`GET /swarms`**: List known swarms from the registry.
- **`POST /swarms`** (`admin`): Body `{ name, base_url, auth_token?, volatile?, metadata? }`. Registers or updates a remote swarm. Non-volatile entries persist across restarts.
- **`GET /swarms/dump`** (`admin`): Logs the active persistent swarm and returns `{ status, swarm_name }`.
- **`POST /swarms/load`** (`admin`): Body `{ json: string }`. Replaces the persistent swarm definition with the provided JSON payload.
- **`POST /interswarm/forward`** (`agent`): Body `{ message: MAILInterswarmMessage }`. Initiate a local task on a remote swarm and begin processing.
- **`POST /interswarm/back`** (`agent`): Body `{ message: MAILInterswarmMessage }`. Resume an existing task on a remote swarm and begin processing.
- **`POST /interswarm/message`** (`user|admin`): Body `{ user_token: string, body: string, targets?: string[], subject?: string, msg_type?: request|broadcast, task_id?: string, routing_info?: object, stream?: boolean, ignore_stream_pings?: boolean }`. Callers MUST provide either `message` or `body`, and either `target_agent` (single-recipient request) or `targets` (broadcast). When `stream=true`, the runtime propagates interswarm streaming metadata (`routing_info.stream = true`) and returns `{ response: MAILMessage, events: ServerSentEvent[] | null }`.

## Swarm Registry

- **Purpose**: Service discovery, endpoint metadata, and health checks.
- **Endpoint model fields**: `swarm_name`, `base_url`, `health_check_url`, `auth_token_ref`, `last_seen`, `is_active`, `metadata`, `volatile`.
- **Persistence**: Non-volatile endpoints MUST be persisted and reloaded on startup. Persistent auth tokens SHOULD be stored as environment variable references and resolved at runtime.
- **Health**: Registries SHOULD perform periodic health checks; inactive endpoints are marked and MAY be skipped for routing.
- **Discovery**: Implementations MAY discover swarms via known discovery URLs and register-found endpoints.

## Authentication and Authorization

- Bearer tokens are required for protected endpoints.
- Tokens SHOULD encode role and identity; systems MAY derive an ID from the caller (`agent|user|admin`) and their token info to isolate MAIL instances.
- For interswarm requests, the registry MAY attach per-swarm auth tokens in the `Authorization` header.

## Error Handling

### Runtime

- MAIL runtime systems SHOULD detect errors and handle them gracefully.
- Runtime-level errors MUST be handled in one of the following ways:
  1. **System response**: The system `{ address_type=system, address={swarm_name} }` sends a `MAILResponse` to the agent that caused the error. The current task otherwise continues normally.
  2. **System broadcast**: The system sends a `MAILBroadcast` to `agent=all` (all agents in the local swarm). This is intended for more swarm-wide issues, or cases where an individual causing agent cannot be determined. The task otherwise continues normally.
  3. **System task completion**: The system sends a `MAILBroadcast` with `msg_type=broadcast_complete` to `agent=all` to prematurely end the current task. This is intended for errors that render task continuation unfeasible. Implementers SHOULD use this sparingly and with caution.
- System error messages SHOULD be easily discernible from normal MAIL messages; no format is mandated by this spec.
  - In the reference implementation, all system error messages have subjects delimited by two colons (e.g. `::task_error::`, `::tool_call_error::`).
  
### Router

- MAIL interswarm routers SHOULD detect errors and route them accordingly.
- If an error occurs while the router is attempting to receive an interswarm message, the error SHOULD propogate back to the server and a non-`200` HTTP response MUST be returned.
- If an error occurs while the router is attempting to send an interswarm message, the error SHOULD propogate back to the runtime in the form of a system error message.

### Server

- MAIL servers SHOULD be sensitive in detecting errors, but robust in handling them.
- If a client does not provide the required authentication in a request to a given endpoint, the server MUST return an HTTP response with status `401`.
- If a client provides an otherwise-malformed request to a given endpoint, the server MUST return an HTTP response with status `400`.
- If the server encounters an unexpected error while handling a client request, it MUST return an HTTP response with status `500`. 

## Security Considerations

- Use TLS[^rfc8446] for all interswarm communication.
- Validate all incoming MAIL/Interswarm payloads against schemas prior to processing.
- **Rate-limit public endpoints**; protect registry mutation operations (admin role).
- **Avoid embedding secrets** in persisted registry; prefer environment variable references.

## Examples and Validation

- **Example payloads**: [spec/examples/*.json](/spec/examples/README.md).
- **Validation helper**: [spec/validate_samples.py](/spec/validate_samples.py) validates inline and file-based samples against both schemas. Run it with `python spec/validate_samples.py`.

## Versioning

- **Protocol version**: 1.2-pre1
- Backward-incompatible changes MUST bump the minor (or major) version and update OpenAPI `info.version`.

## References

[^jsonschema-core]: JSON Schema (Core): https://json-schema.org/draft/2020-12/json-schema-core
[^jsonschema-validation]: JSON Schema (Validation): https://json-schema.org/draft/2020-12/json-schema-validation
[^openapi]: OpenAPI Specification 3.1.0: https://spec.openapis.org/oas/v3.1.0
[^rfc3339]: RFC 3339: Date and Time on the Internet: https://www.rfc-editor.org/rfc/rfc3339
[^rfc4122]: RFC 4122: UUID URN Namespace: https://www.rfc-editor.org/rfc/rfc4122
[^rfc9110]: RFC 9110: HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
[^rfc6750]: RFC 6750: OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
[^rfc8446]: RFC 8446: The Transport Layer Security (TLS) Protocol Version 1.3: https://www.rfc-editor.org/rfc/rfc8446
[^rfc2119]: RFC 2119: Key words for use in RFCs to Indicate Requirement Levels: https://www.rfc-editor.org/rfc/rfc2119
[^rfc8174]: RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words: https://www.rfc-editor.org/rfc/rfc8174
