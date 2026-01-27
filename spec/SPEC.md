# Multi-Agent Interface Layer (MAIL) — Specification

- **Version**: 1.3
- **Date**: January 27, 2026
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
- **MAIL Instance**: Runtime engine handling message queues,  agent interactions, and action calls for a user, admin, or swarm.
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

#### Special agent `all`

- Reserved to represent a shorthand for all agents in the local swarm.
- All `task_complete` messages MUST have recipient agent `all`.
- MAIL agents MUST NOT have the name `all` to ensure proper routing.

### Type `system`

- Reserved for the swarm instance (runtime and router).
- Field `address` MUST be set to the local swarm name.

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

- A **task** is a collection of MAIL messages within one or more swarms associated with a user-defined goal.
- Each task MUST be identified by a unique `task_id`.
- A new task is created when the user sends a message to the swarm with a yet-unused value in the `task_id` field.
- The swarm will continuously process messages with this `task_id` until `task_complete` is called.
- When `task_complete` is called by the swarm where this task originated, the finishing message MUST be returned to the user.

### Multi-Turn

- A user MAY send a message to a swarm with a `task_id` that has been previously completed.
- The swarm instance MUST contain agent communication histories by task and preserve these histories after task completion (see [MAIL Instances](#mail-instances) for more info).
- Upon receiving a message with an existing `task_id`, the swarm instance MUST process messages with this `task_id` until `task_complete` is called.
- Like with new tasks, the swarm instance MUST return the finishing message to the user.

### Ownership & Contributing

- Every MAIL task MUST have a defined `task_owner`.
- The `task_owner` MUST be equal to the swarm instance where the task was created, following the schema defined below.
- Every task MUST have a defined list of `task_contributors`, each contributor following the schema below.
- `task_contributors` MUST include `task_owner`.

#### Schema

- `role:id@swarm`, where:
  - `role` is one of `admin`, `user`, or `swarm`.
  - `id` is the unique identifier of an individual `admin`, `user`, or `swarm` instance.
  - `swarm` is the name of the MAIL swarm.

### Interswarm

- A given swarm MAY collaborate with remote swarms on a task.
- If a remote swarm gets messaged for a task with `task_id` *A*, it MUST use `task_id` *A* in its corresponding task process.
- Interswarm messages MUST include a field `task_owner`, following the schema above.
- Interswarm messages MUST include a field `task_contributors`, following the schema above.
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

## MAIL Instances

- A **MAIL instance** is an individual runtime engine handling message queues, agent interactions, and action calls for a user, admin, or swarm.
- Implementations MUST create discrete instances for each unique, authorized client.
- Instances MUST be listed as the `task_owner` for all tasks created within it (see [Tasks](#tasks) for more info).
- Instances MUST be included in the `task_contributors` list for all tasks created within it (see [Tasks](#tasks) for more info).
- Instances MAY process remote tasks via interswarm messaging; in which case, said instance MUST be included in `task_contributors`.

### Instance Types

#### `admin`

- Represents a MAIL instance belonging to a swarm user with type `admin` (i.e. a swarm administrator).
- Functionally equivalent to instances with type `user`; administrator privileges exist at the server level but not inside MAIL instances.

#### `swarm`

- Represents a MAIL instance belonging to a swarm user with type `agent` (i.e. a remote swarm).
- The name `swarm` is used instead of `agent` because all remote agents in the same swarm MUST share an instance in the local swarm (see [Why:instance type for `swarm` but not for `agent`](/spec/why/01.md) to learn more).
- Swarm instances can contribute to remote tasks.
- Swarm instances MUST NOT create new tasks.

#### `user`

- Represents a MAIL instance belonging a swarm user with type `user` (i.e. a swarm end-user).
- User instances can create and complete defined tasks.
- User instances MUST NOT contribute to remote tasks.

### Runtime

- A MAIL instance MUST contain a unique runtime for handling tasks, message queues, and action calls.
- The runtime MUST maintain agent communication histories scoped by `task_id`.
- Agents within a runtime MAY be provided histories or other swarm information from separate instances; this is not mandated by this spec.
  - Implementers SHOULD exercise extreme caution to ensure potentially-sensitive user information does not cross instance boundaries.

### Router

- A MAIL instance MAY be provided access to a router for interswarm communication.
- The router SHOULD be scoped to the server rather than by instance; interswarm routers like the one in the reference implementation do not need to be user-specific.

### Server

- A MAIL server is an HTTP server that hosts a continuous swarm and manages client instances scoped by type `admin`, `user`, or `swarm`.
- The server MAY contain an interswarm router for managing sending messages to/receiving messages from remote swarms.
- The server MUST include the endpoints specified in [openapi.yaml](/spec/openapi.yaml).
- The server MAY include extra endpoints not included in this spec, so long as they do not interfere with the required endpoints.

## MAIL Tools

### `send_request`

- Create a `MAILMessage` with `msg_type=request` from the given input and send to the specified recipient.
- **Required Parameters**: `target` (string), `subject` (string), `body` (string)
- **Returns**: A message indicating the success or failure of the operation.

### `send_response`

- Create a `MAILMessage` with `msg_type=response` from the given input and send it to the specified recipient.
- **Required Parameters**: `target` (string), `subject` (string), `body` (string)
- **Returns**: A message indicating the success or failure of the operation.

### `send_interrupt`

- Create a `MAILMessage` with `msg_type=interrupt` from the given input and send it to the specified recipient.
- **Required Parameters**: `target` (string), `subject` (string), `body` (string)
- **Returns**: A message indicating the success or failure of the operation.

### `send_broadcast`

- Create a `MAILMessage` with `msg_type=broadcast` and send it to `agent: all`.
- **Required Parameters**: `subject` (string), `body` (string)
- **Returns**: A message indicating the success or failure of the operation.

### `task_complete`

- Create a `MAILMessage` with `msg_type=broadcast_complete` and send it to `agent: all`.
- **Required Parameters**: `finish_message` (string)
- **Returns**: A message indicating the success or failure of the operation.

### `acknowledge_broadcast`

- Store a broadcast in agent memory without sending a response message.
- **Optional Parameters**: `note` (string)
- **Returns**: A message indicating the success or failure of the operation.

### `ignore_broadcast`

- Do not respond to a broadcast or store it in agent memory.
- **Optional Parameters**: `reason` (string)
- **Returns**: A message indicating the success or failure of the operation.

### `await_message`

- Indicate that the agent is finished with its current turn and should be scheduled again once a new MAIL message arrives.
- **Optional Parameters**: `reason` (string)
- **Returns**: A message indicating the success or failure of the operation.

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

- Interswarm-enabled deployments MUST maintain a registry of remote swarms that can be contacted.
- Registered swarms marked as `volatile` MUST NOT persist in the registry on server shutdown.
- Deployment administrators MAY register remote swarms by using the `POST /swarms/register` endpoint.
  - This endpoint MUST accept the following parameters:
    - `swarm_name` (string): The name of the remote MAIL swarm to register.
    - `base_url` (string): The base URL of the swarm to register.
  - Furthermore, this endpoint MAY accept the following parameters:
    - `volatile` (bool): Whether or not this swarm should persist in the registry.
    - `metadata` (object): Extra swarm metadata.
  - Upon registration, the deployment MUST attempt to retrieve further metadata from the remote swarm:
    - `version` (string): The version of the MAIL protocol this swarm is operating on.
    - `last_seen` (string): The UTC timestamp of when this swarm was last seen.
    - `swarm_description` (string): A natural-language description of the swarm and its functionality.
    - `keywords` (array): A list of keyword strings for this swarm.
- The endpoint `GET /swarms` MUST provide a list of all public remote swarms in this deployment's registry.
  - Swarms that are not `public` MUST NOT be listed in the response for `GET /swarms`.
  - Each swarm listed in this endpoint response MUST contain the following variables:
    - `swarm_name` (string): Same as above.
    - `base_url` (string): Same as above.
    - `version` (string): Same as above.
    - `last_seen` (string): Same as above.
    - `swarm_description` (string): Same as above.
    - `keywords` (array): Same as above.
  - Furthermore, each swarm listed MAY contain the following variables:
    - `latency` (float): The latency of this swarm in seconds.
    - `metadata` (object): Extra swarm metadata.
  - This endpoint SHOULD NOT expose swarm parameters such as `auth_token_ref`, `public`, and `volatile`.

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

- **Protocol version**: 1.3
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
