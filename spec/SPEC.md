# Multi-Agent Interface Layer (MAIL) — Specification

- **Version**: 2.0-pre1
- **Date**: February 26, 2026
- **Status**: Open to feedback
- **Scope**: Defines the data model, addressing, routing semantics, and REST transport for interoperable communication among autonomous agents within and across swarms.
- **Authors**: Addison Kline (GitHub: [@addisonkline](https://github.com/addisonkline)), Will Hahn (GitHub: [@wsfhahn](https://github.com/wsfhahn)), Ryan Heaton (GitHub: [@rheaton64](https://github.com/rheaton64)), Jacob Hahn (GitHub: [@jacobtohahn](https://github.com/jacobtohahn))

## Table of Contents
- [Multi-Agent Interface Layer (MAIL) — Specification](#multi-agent-interface-layer-mail--specification)
  - [Table of Contents](#table-of-contents)
  - [1. Normative References](#1-normative-references)
  - [2. Terminology](#2-terminology)
  - [3. Requirements Language](#3-requirements-language)
  - [4. Conformance](#4-conformance)
  - [5. Data Model](#5-data-model)
    - [5.1 `MAILAddress`](#51-mailaddress)
    - [5.2 `MAILMessage`](#52-mailmessage)
    - [5.3 `MAILInterswarmMessage` (spec/MAIL-interswarm.schema.json)](#53-mailinterswarmmessage-specmail-interswarmschemajson)
  - [6. Addressing](#6-addressing)
    - [6.1 Type `admin`](#61-type-admin)
    - [6.2 Type `agent`](#62-type-agent)
      - [6.2.4 Special agent `all`](#624-special-agent-all)
    - [6.3 Type `system`](#63-type-system)
    - [6.4 Type `user`](#64-type-user)
  - [7. Message Types](#7-message-types)
  - [8. Message Semantics](#8-message-semantics)
    - [8.1 Priority and Ordering](#81-priority-and-ordering)
    - [8.2 Recipients](#82-recipients)
    - [8.3 Subject Encoding](#83-subject-encoding)
    - [8.4 Body Encoding](#84-body-encoding)
  - [9. Tasks](#9-tasks)
    - [9.1 Multi-Turn Tasks](#91-multi-turn-tasks)
    - [9.2 Task Ownership and Contributing](#92-task-ownership-and-contributing)
    - [9.3 Task Owner and Contributor Schema](#93-task-owner-and-contributor-schema)
    - [9.4 Interswarm Tasks](#94-interswarm-tasks)
  - [10. Routing Semantics](#10-routing-semantics)
    - [10.1 Local Routing](#101-local-routing)
    - [10.2 Interswarm Routing](#102-interswarm-routing)
  - [11. MAIL Instances](#11-mail-instances)
    - [11.1 Instance Types](#111-instance-types)
      - [11.1.1 Type `admin`](#1111-type-admin)
      - [11.1.2 Type `swarm`](#1112-type-swarm)
      - [11.1.3 Type `user`](#1113-type-user)
    - [11.2 Runtime](#112-runtime)
    - [11.3 Router](#113-router)
    - [11.4 Server](#114-server)
  - [12. REST Transport](#12-rest-transport)
    - [12.1 Security](#121-security)
    - [12.2 Endpoints](#122-endpoints)
  - [13. Swarm Registry](#13-swarm-registry)
  - [14. Authentication and Authorization](#14-authentication-and-authorization)
  - [15. Error Handling](#15-error-handling)
    - [15.1 Runtime](#151-runtime)
    - [15.2 Router](#152-router)
    - [15.3 Server](#153-server)
  - [16. Security Considerations](#16-security-considerations)
  - [17. Examples and Validation](#17-examples-and-validation)
  - [18. Versioning](#18-versioning)
  - [References](#references)

## 1. Normative References

- **1.1** Core schema: [spec/MAIL-core.schema.json](/spec/MAIL-core.schema.json) (JSON Schema[^jsonschema-core][^jsonschema-validation])
- **1.2** Interswarm schema: [spec/MAIL-interswarm.schema.json](/spec/MAIL-interswarm.schema.json) (JSON Schema)
- **1.3** REST API: [spec/openapi.yaml](/spec/openapi.yaml) (OpenAPI 3.1[^openapi])

## 2. Terminology

- **2.1** “Action”: An agent-controlled process (for example, a tool call) that is not defined within MAIL.
- **2.2** "Admin": A user with extended privileges inside a given MAIL HTTP(S)[^rfc9110] server.
- **2.3** "Agent": An autonomous process participating in MAIL.
- **2.4** "Entrypoint": An agent capable of receiving MAIL messages directly from a user or admin.
- **2.5** "Interswarm": Communication between agents in different swarms via HTTP(S).
- **2.6** "MAIL Instance": Runtime system handling message queues, agent interactions, and action calls scoped to an individual user, admin, or swarm.
- **2.7** "Supervisor": An agent capable of completing a task.
- **2.8** "Swarm": A named deployment domain hosting a set of agents and providing a system to handle agent communication, action execution, and lifecycles through discrete instances.
- **2.9** "Task": A user-defined query sent to a swarm entrypoint that agents complete through collaboration over MAIL.
- **2.10** "User": A human or external client initiating a task.

## 3. Requirements Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119[^rfc2119] and RFC 8174[^rfc8174] when, and only when, they appear in all capitals.

## 4. Conformance

- **4.1** Producers MUST emit messages conforming to the JSON Schemas referenced in section 1.
- **4.2** Consumers MUST validate at least the presence and type of `msg_type`, `id`, `timestamp`, and the required fields for the bound payload type.
- **4.3** Implementations of HTTP transport MUST conform to [spec/openapi.yaml](/spec/openapi.yaml) (OpenAPI 3.1).
- **4.4** Interswarm implementations MUST accept both request and response wrappers and deliver payloads to local MAIL processing.

## 5. Data Model

All types are defined in [spec/MAIL-core.schema.json](/spec/MAIL-core.schema.json) unless noted.

### 5.1 `MAILAddress`

- **5.1.1** Required fields: `addr_type` (enum: `agent|admin|user|system`), `address` (string).
- **5.1.2** No `additionalProperties`.

### 5.2 `MAILMessage`

- **5.2.1** Required fields: `id` (uuid), `timestamp` (date-time[^rfc3339]), `msg_type` (enum: `direct|broadcast|interrupt|task_complete`), `recipients` (array), `subject` (string), `body` (string).

### 5.3 `MAILInterswarmMessage` ([spec/MAIL-interswarm.schema.json](/spec/MAIL-interswarm.schema.json))

- **5.3.1** Required fields: `message_id` (string), `source_swarm` (string), `target_swarm` (string), `timestamp` (date-time), `payload` (object), `task_owner` (string), `task_contributors` (array).
- **5.3.2** Optional fields: `auth_token` (string), `metadata` (object).
- **5.3.3** Payload binding mirrors `MAILMessage` (payload is a core MAIL payload, not the outer wrapper).

## 6. Addressing

- **6.0.1** Local address: `name`
- **6.0.2** Remote (interswarm) address: `name@swarm`
  
### 6.1 Type `admin`

- **6.1.1** Addresses with `addr_type=admin` MUST be reserved for system administrators of a given swarm.
- **6.1.2** Field `address` MUST be set to a unique identifier for each administrator.
- **6.1.3** Field `address` MAY be a traditional username if those are fully unique; the reference implementation uses randomly-generated UUIDs for consistency.

### 6.2 Type `agent`

- **6.2.1** Addresses with `addr_type=agent` MUST be reserved for autonomous agents participating in MAIL.
- **6.2.2** Field `address` is used to identify agents; values of `address` MUST be unique within a swarm.
- **6.2.3** Field `address` MAY follow interswarm schema.

#### 6.2.4 Special agent `all`

- **6.2.4.1** Addresses with `addr_type=agent` and `address=all` MUST be reserved to represent a shorthand for all agents in the local swarm.
- **6.2.4.2** All `task_complete` messages MUST have `recipients=['all']`.
- **6.2.4.3** MAIL agents MUST NOT have the name `all` to ensure proper routing.

### 6.3 Type `system`

- **6.3.1** Addresses with `addr_type=system` MUST be reserved for the swarm instance (runtime and router).
- **6.3.2** For a given swarm, the field `address` MUST be set to the local swarm name.

### 6.4 Type `user`

- **6.4.1** Addresses with `addr_type=user` MUST be reserved for end-users of a given MAIL swarm.
- **6.4.2** Field `address` MUST be set to a unique identifier for each user.
- **6.4.3** Field `address` MAY be a traditional username if those are fully unique within a swarm; the reference implementation uses randomly-generated UUIDs for consistency.

## 7. Message Types

TODO

## 8. Message Semantics

### 8.1 Priority and Ordering

- **Tier 1 (highest)**: Message of any `msg_type` from addresses with `addr_type=system`.
- **Tier 2**: Messages of any `msg_type` from addresses with `addr_type=admin|user`.
- **Tier 3**: Messages with `msg_type=interrupt` from addresses with `addr_type=agent`.
- **Tier 4**: Messages with `msg_type=broadcast` from addresses with `addr_type=agent`.
- **Tier 5 (lowest)**: Messages with `msg_type=direct` from addresses with `addr_type=agent`.
- Ties are ordered by `timestamp` (FIFO per priority class).

### 8.2 Recipients

- **8.2.1** All message types accept an array of `recipients`, each entry representing an agent by address (string).
- **8.2.2** `recipients` MAY have size 1, for instance in the case of a `direct` message from one agent to another, or in a `task_complete` message to `agent=all`.

### 8.3 Subject Encoding

- **8.3.1** `subject` is a free-form string; no schema for `subject` is mandated by this spec.
- **8.3.2** When the sender has `addr_type=agent`, the implementing system SHOULD allow the sending agent to decide on the content of `subject` based on the context.
- **8.3.3** When the sender has `addr_type=system`, the implementing system SHOULD make the value of `subject` easily-discernable from an agent message.
  - The reference implementation does this by wrapping all error types in two semicolons (`::tool_call_error::`, `::runtime_error::`, etc.)

### 8.4 Body Encoding

- **8.4.1** `body` is a free-form string; no schema for `body` is mandated by this spec.
- **8.4.2** Implementing systems MAY include structured content within `body` (e.g., Markdown or XML snippets).

## 9. Tasks

- **9.0.1** A task is a user-defined query sent to a swarm entrypoint that agents complete through collaboration over MAIL (see section 2.9).
- **9.0.2** Each task MUST be identified by a unique `task_id`.
- **9.0.3** Tasks are scoped by instance; each `task_id` MUST uniquely identify a specific existing task in said instance.
- **9.0.4** A new task MUST be created when the user sends a message to the swarm with a yet-unused value in the `task_id` field.
- **9.0.5** The swarm MUST continuously process messages with this `task_id` until `task_complete` is called.
- **9.0.6** When `task_complete` is called by the swarm where this task originated, the finishing message MUST be returned to the user.

### 9.1 Multi-Turn Tasks

- **9.1.1** A user MAY send a message to a swarm with a `task_id` that has been previously completed (i.e., the supervisor has already called `task_complete`).
- **9.1.2** The swarm instance MUST contain agent communication histories by task and preserve these histories after task completion (see section 11).
- **9.1.3** Upon receiving a message with an existing `task_id`, the swarm instance MUST process messages with this `task_id` until `task_complete` is called.
- **9.1.4** Like with new tasks, the swarm instance MUST return the finishing message to the user.

### 9.2 Task Ownership and Contributing

- **9.2.1** Every MAIL task MUST have a defined `task_owner`.
- **9.2.2** The `task_owner` MUST be equal to the swarm instance where the task was created, following the schema defined in section 9.3.
- **9.2.3** Every task MUST have a defined list of `task_contributors`, each contributor following the schema defined in section 9.3.
- **9.2.4** `task_contributors` MUST include `task_owner`.

### 9.3 Task Owner and Contributor Schema

- Task owner and contributor IDs MUST follow the format `role:id@swarm`, where:
  - `role` is one of `admin`, `user`, or `swarm`.
  - `id` is the unique identifier of an individual `admin`, `user`, or `swarm` instance.
  - `swarm` is the name of the MAIL swarm.

### 9.4 Interswarm Tasks

- **9.4.1** A given swarm MAY collaborate with remote swarms on a task.
- **9.4.2** If a remote swarm gets messaged for a task with `task_id=example`, it MUST use `task_id=example` in its corresponding task process.
- **9.4.3** Interswarm messages MUST include a field `task_owner`, following the schema defined in section 9.3.
- **9.4.4** Interswarm messages MUST include a field `task_contributors`, following the schema defined in section 9.3.
- **9.4.5** If a remote swarm calls `task_complete`, the finish message MUST be returned to the swarm instance that called it.
- **9.4.6** When a remote swarm calls `task_complete`, said swarm MUST be added to `task_contributors`.
- **9.4.7** When the `task_owner` instance calls `task_complete`, the remote swarms that contributed MUST be notified.

## 10. Routing Semantics

- **10.0.1** Implementing systems SHOULD impose limits on the agents reachable by any given agent.
  - The reference implementation requires a field `comm_targets: list[str]` for every agent, which serves this purpose.

### 10.1 Local Routing

- **10.1.1** If no swarm qualifier is present in a given message, or the qualifier matches the local swarm, the message MUST be delivered to local agent(s) by name.
- **10.1.2** Unknown local agents SHOULD be logged and ignored.

### 10.2 Interswarm Routing

- **10.2.1** If a swarm qualifier is present in a given message (i.e., one or more addresses follow the format `agent-name@swarm-name`), the message MUST be delivered to the corresponding agent(s) by name. 
- **10.2.2** If a remote agent does not exist or is otherwise unreachable, the sending agent MUST be notified.

## 11. MAIL Instances

- **11.0.1** A MAIL instance is a runtime system handling message queues, agent interactions, and action calls scoped to an individual user, admin, or swarm (see section 2.6).
- **11.0.2** Implementing systems MUST create and manage discrete instances for each unique, authorized client.
- **11.0.3** Instances MUST be listed as the `task_owner` for all tasks created within it (see section 9 for more info).
- **11.0.4** Instances MUST be included in the `task_contributors` list for all tasks created within it (see section 9 for more info).
- **11.0.5** Instances MAY process remote tasks via interswarm messaging; in which case, said instance MUST be included in `task_contributors`.

### 11.1 Instance Types

#### 11.1.1 Type `admin`

- **11.1.1.1** Instances with type `admin` MUST be reserved for those that belong to a swarm user with type `addr_type=admin` (i.e. a swarm administrator).
- **11.1.1.2** These instances are functionally equivalent to instances with type `user`; administrator privileges exist at the server level but not inside MAIL instances.

#### 11.1.2 Type `swarm`

- **11.1.2.1** Instances with type `swarm` MUST be reserved for those that belong to a swarm user with type `agent` (corresponding to an agent in a remote swarm).
- **11.1.2.2** The name `swarm` is used instead of `agent` because all remote agents in the same swarm MUST share an instance in the local swarm (see [Why:instance type for `swarm` but not for `agent`](/spec/why/01.md) to learn more).
- **11.1.2.3** Instances with type `swarm` SHOULD contribute to remote tasks.
- **11.1.2.4** Instances with type `swarm` MUST NOT create new tasks; all tasks operated on MUST be remotely-owned.

#### 11.1.3 Type `user`

- **11.1.3.1** Instances with type `user` MUST be reserved for those that belong to a swarm user with type `user` (i.e. a swarm end-user).
- **11.1.3.2** Instances with type `user` MAY create and complete defined tasks.
- **11.1.3.3** Instances with type `user` MUST NOT contribute to remote tasks.

### 11.2 Runtime

- **11.2.1** A MAIL instance MUST contain a unique runtime for handling tasks, message queues, and actions.
- **11.2.2** The runtime MUST maintain agent communication histories scoped by `task_id`.
- **12.2.3** Agents within a runtime MAY be provided histories or other swarm information from separate instances; this is not mandated by this spec.
  - Implementing systems SHOULD exercise extreme caution to ensure potentially-sensitive user information does not cross instance boundaries.

### 11.3 Router

- **11.3.1** A MAIL instance MAY be provided access to a router for interswarm communication.
- **11.3.2** The router SHOULD be scoped to the server rather than by instance; interswarm routers like the one in the reference implementation do not need to be user-specific.

### 11.4 Server

- **11.4.1** A MAIL server is an HTTP server that hosts a continuous swarm and manages client instances scoped by type `admin`, `user`, or `swarm`.
- **11.4.2** The server MAY contain an interswarm router for managing sending messages to/receiving messages from remote swarms.
- **11.4.3** The server MUST include the endpoints specified in [openapi.yaml](/spec/openapi.yaml).
- **11.4.4** The server MAY include extra endpoints not included in this spec, so long as they do not interfere with the required endpoints.

## 12. REST Transport

**12.0.1** Authoritative contract: [spec/openapi.yaml](/spec/openapi.yaml) (OpenAPI 3.1).

### 12.1 Security

- **12.1.1** Individual MAIL servers MUST use HTTP Bearer[^rfc6750] authentication.
  **12.1.2** Each bearer token MUST correspond to exactly one of the following roles:
  - `agent`: MAY call `/interswarm/forward`, `/interswarm/back`.
  - `user`: MAY call `/status`, `/whoami`, `/message`, `/swarms`, `/interswarm/message`.
  - `admin`: inherits `user` access and MAY additionally call `/swarms` (POST), `/swarms/dump`, `/swarms/load`.

### 12.2 Endpoints

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

## 13. Swarm Registry

- **13.1** Interswarm-enabled deployments MUST maintain a registry of remote swarms that can be contacted.
- **13.2** Registered swarms marked as `volatile` MUST NOT persist in the registry on server shutdown.
- **13.3** Deployment administrators MAY register remote swarms by using the `POST /swarms/register` endpoint.
  - **13.3.1** This endpoint MUST accept the following parameters:
    - `swarm_name` (string): The name of the remote MAIL swarm to register.
    - `base_url` (string): The base URL of the swarm to register.
  - **13.3.2** Furthermore, this endpoint MAY accept the following parameters:
    - `volatile` (bool): Whether or not this swarm should persist in the registry.
    - `metadata` (object): Extra swarm metadata.
  - **13.3.3** Upon registration, the deployment MUST attempt to retrieve further metadata from the remote swarm:
    - `version` (string): The version of the MAIL protocol this swarm is operating on.
    - `last_seen` (string): The UTC timestamp of when this swarm was last seen.
    - `swarm_description` (string): A natural-language description of the swarm and its functionality.
    - `keywords` (array): A list of keyword strings for this swarm.
- **13.4** The endpoint `GET /swarms` MUST provide a list of all public remote swarms in this deployment's registry.
  - **13.4.1** Swarms with `public=false` MUST NOT be listed in the response for `GET /swarms`.
  - **13.4.2** Each swarm listed in this endpoint response MUST contain the following variables:
    - `swarm_name` (string): Same as above.
    - `base_url` (string): Same as above.
    - `version` (string): Same as above.
    - `last_seen` (string): Same as above.
    - `swarm_description` (string): Same as above.
    - `keywords` (array): Same as above.
  - **13.4.3** Furthermore, each swarm listed MAY contain the following variables:
    - `latency` (float): The latency of this swarm in seconds.
    - `metadata` (object): Extra swarm metadata.
  - **13.4.4** This endpoint SHOULD NOT expose swarm parameters such as `auth_token_ref`, `public`, and `volatile`.

## 14. Authentication and Authorization

- **14.1** Bearer tokens MUST be required for protected endpoints.
- **14.2** Bearer tokens SHOULD encode role and identity; systems MAY derive an ID from the caller (`agent|user|admin`) and their token info to isolate MAIL instances.
- **14.3** For interswarm requests, the registry MAY attach per-swarm authorization tokens in the `Authorization` header.

## 15. Error Handling

### 15.1 Runtime

- **15.1.1** MAIL runtime systems SHOULD detect errors and handle them gracefully.
- **15.1.2** Runtime-level errors MUST be handled in one of the following ways:
  1. **System response**: The system `{ addr_type=system, address={swarm_name} }` sends a message with `msg_type=direct` to the agent that caused the error. The current task otherwise continues normally.
  2. **System broadcast**: The system sends a message with `msg_type=broadcast` to `agent=all` (all agents in the local swarm). This is intended for more swarm-wide issues, or cases where an individual causing agent cannot be determined. The task otherwise continues normally.
  3. **System task completion**: The system sends a message with `msg_type=task_complete` to `agent=all` to prematurely end the current task. This is intended for errors that render task continuation unfeasible. Implementers SHOULD use this sparingly and with caution.
- **15.1.3** System error messages SHOULD be easily discernible from normal MAIL messages; no format is mandated by this spec.
  - In the reference implementation, all system error messages have subjects delimited by two colons (e.g. `::task_error::`, `::tool_call_error::`).
  
### 15.2 Router

- **15.2.1** MAIL interswarm routers SHOULD detect errors and route them accordingly.
- **15.2.2** If an error occurs while the router is attempting to receive an interswarm message, the error SHOULD propogate back to the server and a non-`200` HTTP response MUST be returned to the client.
- **15.2.3** If an error occurs while the router is attempting to send an interswarm message, the error SHOULD propogate back to the sending agent in the form of a system error message.

### 15.3 Server

- **15.3.1** MAIL servers SHOULD be sensitive in detecting errors, but robust in handling them.
- **15.3.2** If a client does not provide the required authentication in a request to a given endpoint, the server MUST return an HTTP response with status code `401`.
- **15.3.3** If a client provides an otherwise-malformed request to a given endpoint, the server MUST return an HTTP response with status code `400`.
- **15.3.4** If the server encounters an unexpected error while handling a client request, it MUST return an HTTP response with status code `500`. 

## 16. Security Considerations

- **16.1** Implementing systems SHOULD use TLS[^rfc8446] for all interswarm communication.
- **16.2** Implementing systems SHOULD validate all incoming MAIL/Interswarm payloads against schemas prior to processing.
- **16.3** Implementing systems SHOULD rate-limit public endpoints and protect registry mutation operations (admin role).
- **16.4** Implementing systems SHOULD avoid embedding secrets in persisted registry; prefer environment variable references.

## 17. Examples and Validation

- Example payloads: [spec/examples/*.json](/spec/examples/README.md).
- Validation helper: [spec/validate_samples.py](/spec/validate_samples.py) validates inline and file-based samples against both schemas. Run it with `python spec/validate_samples.py`.

## 18. Versioning

- **18.1** Current protocol version: 2.0-pre1
- **18.2** Backward-incompatible changes MUST bump the minor (or major) version and update OpenAPI `info.version`.

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
