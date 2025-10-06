# Multi-Agent Interface Layer (MAIL) — Specification

- **Version**: 1.1-pre2
- **Date**: October 7, 2025
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

- **Fields**: `address_type` (enum: `agent|user|system`), `address` (string).
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

- **Required**: `message_id` (string), `source_swarm` (string), `target_swarm` (string), `timestamp` (date-time), `payload` (object), `msg_type` (enum: `request|response|broadcast|interrupt`).
- **Optional**: `auth_token` (string), `metadata` (object).
- Payload binding mirrors `MAILMessage` (payload is a core MAIL payload, not the outer wrapper).

## Addressing

- **Local agent**: `agent-name`
- **Interswarm agent**: `agent-name@swarm-name`
- `MAILAddress` MUST include `address_type` and `address`.

## Message Semantics

### Priority and Ordering

- **Tier 1 (highest)**: `*` from `system`
- **Tier 2**: `*` from `user`
- **Tier 3**: `interrupt` from `agent`
- **Tier 4**: `broadcast` from `agent`
- **Tier 5 (lowest)**: `request|response` from `agent`
- Ties are ordered by `timestamp` (FIFO per priority class).

### Recipients

- **Single-recipient messages** use `recipient` (`MAILRequest`/`MAILResponse`).
- **Multi-recipient messages** use `recipients` (`MAILBroadcast`/`MAILInterrupt`).
- Special recipient `agent: all` indicates broadcast to all local agents. Therefore, every agent MUST NOT have `address=all`.

### Task Lifecycle

- A **user task** is identified by `task_id`.
- The task **completes** when a `broadcast_complete` for the corresponding `task_id` is produced by a supervisor in the swarm that initiated it.
- Systems using `submit_and_wait` MUST resolve awaiting futures only when `broadcast_complete` for that `task_id` is observed.
- A given task MAY be referenced in a future request from the calling user, even after `task_complete`. Resumed tasks MUST also resolve only on `task_complete`.

### Body Encoding

- `body` is free-form string. Systems MAY include structured content (e.g., XML snippets) for prompt formatting; no XML semantics are mandated by this spec.

## Routing Semantics

### Local Routing

- If no swarm qualifier is present, or the qualifier matches the local swarm, the message MUST be delivered to local agent(s) by name.
- Unknown local agents SHOULD be logged and ignored.

### Interswarm Routing

- If a recipient address includes `@<other-swarm>`, the message MUST be wrapped in `MAILInterswarmMessage` and sent to the remote swarm’s `/interswarm/message` endpoint.
- **Outbound rewrite rules**:
  - Sender address SHOULD be rewritten to include the local swarm (e.g., `supervisor@local-swarm`).
  - `sender_swarm` and `recipient_swarm` SHOULD be set accordingly.
  - For request/response flows, routers SHOULD set `metadata.expect_response = true` when a response is expected.
- **Inbound response handling**:
  - The origin swarm MUST deliver interswarm responses back into the local MAIL pipeline for processing and task finalization.

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

## REST Transport

**Authoritative contract**: [spec/openapi.yaml](/spec/openapi.yaml) (OpenAPI 3.1[^openapi]).

### Security

- HTTP Bearer[^rfc6750] authentication.
- **Roles**:
  - `agent`: may call `/interswarm/message`, `/interswarm/response`.
  - `user`: may call `/status`, `/whoami`, `/message`, `/swarms`, `/interswarm/send`.
  - `admin`: inherits `user` access and may additionally call `/swarms` (POST), `/swarms/dump`, `/swarms/load`.

### Endpoints

- **`GET /`**: Server metadata. Returns `{ name, status, version }`.
- **`GET /health`**: Health probe for interswarm peers. Returns `{ status, swarm_name, timestamp }`.
- **`GET /status`** (`user|admin`): Server status, including swarm and user-instance indicators.
- **`GET /whoami`** (`user|admin`): Returns `{ username, role }` derived from the presented token. Useful for clients to confirm identity/role assignments.
- **`POST /message`** (`user|admin`): Body `{ body: string, subject?: string, task_id?: string, entrypoint?: string, show_events?: boolean, stream?: boolean, resume_from?: user_response|breakpoint_tool_call, kwargs?: object }`. Creates a MAIL request to the swarm's default entrypoint (or user-specified `entrypoint`) and returns the final `response.body` when `broadcast_complete` resolves. When `stream=true`, the server responds with `text/event-stream` SSE events until completion.
- **`GET /swarms`**: List known swarms from the registry.
- **`POST /swarms`** (`admin`): Body `{ name, base_url, auth_token?, volatile?, metadata? }`. Registers or updates a remote swarm. Non-volatile entries persist across restarts.
- **`GET /swarms/dump`** (`admin`): Logs the active persistent swarm and returns `{ status, swarm_name }`.
- **`POST /swarms/load`** (`admin`): Body `{ json: string }`. Replaces the persistent swarm definition with the provided JSON payload.
- **`POST /interswarm/message`** (`agent`): Body is `MAILInterswarmMessage`. Delivers the wrapped payload into local MAIL and returns a `MAILMessage` response for request/response flows.
- **`POST /interswarm/response`** (`agent`): Body is `MAILMessage`. Submits a remote swarm response back into the origin MAIL pipeline; returns `{ status, task_id }`.
- **`POST /interswarm/send`** (`user|admin`): Body `{ user_token: string, body: string, targets?: string[], subject?: string, msg_type?: request|broadcast, task_id?: string, routing_info?: object, stream?: boolean, ignore_stream_pings?: boolean }`. Callers MUST provide either `message` or `body`, and either `target_agent` (single-recipient request) or `targets` (broadcast). When `stream=true`, the runtime propagates interswarm streaming metadata (`routing_info.stream = true`) and returns `{ response: MAILMessage, events: ServerSentEvent[] | null }`.

## Swarm Registry

- **Purpose**: Service discovery, endpoint metadata, and health checks.
- Endpoint model fields: `swarm_name`, `base_url`, `health_check_url`, `auth_token_ref`, `last_seen`, `is_active`, `metadata`, `volatile`.
- **Persistence**: Non-volatile endpoints MUST be persisted and reloaded on startup. Persistent auth tokens SHOULD be stored as environment variable references and resolved at runtime.
- **Health**: Registries SHOULD perform periodic health checks; inactive endpoints are marked and MAY be skipped for routing.
- **Discovery**: Implementations MAY discover swarms via known discovery URLs and register-found endpoints.

## Authentication and Authorization

- Bearer tokens are required for protected endpoints.
- Tokens SHOULD encode role and identity; systems MAY derive `user_id` or `agent_id` from token info to isolate MAIL instances.
- For interswarm requests, the registry MAY attach per-swarm auth tokens in the `Authorization` header.

## Error Handling

- Router errors SHOULD be returned as `MAILMessage` with `msg_type = response`, `sender = {"address_type": "system", "address": {swarm_name}}`, and `subject = "Router Error"`.
- Unknown recipients and inactive swarms SHOULD be logged; callers MAY receive a router error response.

## Security Considerations

- Use TLS[^rfc8446] for all inter-swarm communication.
- Validate all incoming MAIL/Interswarm payloads against schemas prior to processing.
- **Rate-limit public endpoints**; protect registry mutation operations (admin role).
- **Avoid embedding secrets** in persisted registry; prefer environment variable references.

## Examples and Validation

- **Example payloads**: [spec/examples/*.json](/spec/examples/README.md).
- **Validation helper**: [spec/validate_samples.py](/spec/validate_samples.py) validates inline and file-based samples against both schemas. Run it with `python spec/validate_samples.py`.

## Versioning

- **Protocol version**: 1.1-pre2
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
