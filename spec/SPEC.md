# Multi-Agent Interface Layer (MAIL) — Draft Specification

- **Version**: 0.1.0 (draft)
- **Status**: Draft for review
- **Scope**: Defines the data model, addressing, routing semantics, runtime, and REST transport for interoperable communication among autonomous agents within and across swarms.
- **Authors**: Addison Kline (GitHub: [@addisonkline](https://github.com/addisonkline)), Will Hahn (GitHub: [@wsfhahn](https://github.com/wsfhahn)), Ryan Heaton (GitHub: [@rheaton64](https://github.com/rheaton64)), Jacob Hahn (GitHub: [@jacobtohahn](https://github.com/jacobtohahn))

## Normative References

- Core schema: `spec/MAIL-core.schema.json`
- Interswarm schema: `spec/MAIL-interswarm.schema.json`
- REST API: `spec/openapi.yaml` (OpenAPI 3.1)

## Terminology

- Agent: Autonomous process participating in MAIL.
- User: Human or external client initiating a task.
- Swarm: Named deployment domain hosting a set of agents.
- MAIL Instance: Runtime engine handling message queues and agent interactions for a user or swarm.
- Interswarm: Communication between agents in different swarms via HTTP.

## Conformance

- Producers MUST emit messages conforming to the JSON Schemas referenced above.
- Consumers MUST validate at least the presence and type of `msg_type`, `id`, `timestamp`, and the required fields for the bound payload type.
- Implementations of HTTP transport MUST conform to `spec/openapi.yaml`.
- Interswarm implementations MUST accept both request and response wrappers and deliver payloads to local MAIL processing.

## Data Model

All types are defined in `spec/MAIL-core.schema.json` unless noted.

### MAILAddress

- Fields: `address_type` (enum: `agent|user|system`), `address` (string).
- No `additionalProperties`.

### MAILRequest

- Required: `task_id` (uuid), `request_id` (uuid), `sender` (MAILAddress), `recipient` (MAILAddress), `subject` (string), `body` (string).
- Optional: `sender_swarm` (string), `recipient_swarm` (string), `routing_info` (object).
- No `additionalProperties`.

### MAILResponse

- Required: `task_id` (uuid), `request_id` (string), `sender`, `recipient`, `subject`, `body`.
- Optional: `sender_swarm`, `recipient_swarm`, `routing_info`.
- No `additionalProperties`.

### MAILBroadcast

- Required: `task_id` (uuid), `broadcast_id` (uuid), `sender`, `recipients` (array of MAILAddress, minItems=1), `subject`, `body`.
- Optional: `sender_swarm`, `recipient_swarms` (array of string), `routing_info`.
- No `additionalProperties`.

### MAILInterrupt

- Required: `task_id` (uuid), `interrupt_id` (uuid), `sender`, `recipients` (array of MAILAddress, minItems=1), `subject`, `body`.
- Optional: `sender_swarm`, `recipient_swarms`, `routing_info`.
- No `additionalProperties`.

### MAILMessage

- Required: `id` (uuid), `timestamp` (date-time), `message` (object), `msg_type` (enum: `request|response|broadcast|interrupt|broadcast_complete`).
- Conditional binding:
  - `request` → `message` MUST be MAILRequest
  - `response` → `message` MUST be MAILResponse
  - `broadcast` → `message` MUST be MAILBroadcast
  - `interrupt` → `message` MUST be MAILInterrupt
  - `broadcast_complete` → `message` MUST be MAILBroadcast

### MAILInterswarmMessage (spec/MAIL-interswarm.schema.json)

- Required: `message_id` (string), `source_swarm` (string), `target_swarm` (string), `timestamp` (date-time), `payload` (object), `msg_type` (enum: `request|response|broadcast|interrupt`).
- Optional: `auth_token` (string), `metadata` (object).
- Payload binding mirrors `MAILMessage` (payload is a core MAIL payload, not the outer wrapper).

## Addressing

- Local agent: `agent-name`
- Interswarm agent: `agent-name@swarm-name`
- MAILAddress MUST include `address_type` and `address`.
- Implementations MAY accept bare strings for backward compatibility, but SHOULD emit full MAILAddress objects.

## Message Semantics

### Priority and Ordering

- Highest: `interrupt`, `broadcast_complete`
- Medium: `broadcast`
- Lower: `request`, `response`
- Ties are ordered by `timestamp` (FIFO per priority class).

### Recipients

- Single-recipient messages use `recipient` (MAILRequest/MAILResponse).
- Multi-recipient messages use `recipients` (MAILBroadcast/MAILInterrupt).
- Special recipient `agent: all` indicates broadcast to all local agents.

### Task Lifecycle

- A user task is identified by `task_id`.
- The task completes when a `broadcast_complete` for the corresponding `task_id` is produced (typically by the supervisor).
- Systems using `submit_and_wait` MUST resolve awaiting futures only when `broadcast_complete` for that `task_id` is observed.

### Body Encoding

- `body` is free-form string. Systems MAY include structured content (e.g., XML snippets) for prompt formatting; no XML semantics are mandated by this spec.

## Routing Semantics

### Local Routing

- If no swarm qualifier is present, or the qualifier matches the local swarm, the message MUST be delivered to local agent(s) by name.
- Unknown local agents SHOULD be logged and ignored.

### Interswarm Routing

- If a recipient address includes `@<other-swarm>`, the message MUST be wrapped in `MAILInterswarmMessage` and sent to the remote swarm’s `/interswarm/message` endpoint.
- Outbound rewrite rules:
  - Sender address SHOULD be rewritten to include the local swarm (e.g., `supervisor@local-swarm`).
  - `sender_swarm` and `recipient_swarm` SHOULD be set accordingly.
  - For request/response flows, routers SHOULD set `metadata.expect_response = true` when a response is expected.
- Inbound response handling:
  - The origin swarm MUST deliver interswarm responses back into the local MAIL pipeline for supervisor processing.

## Runtime Model

- A MAIL Instance:
  - Maintains per-agent message histories for context.
  - Executes agent tool calls; supervisor tool outputs are translated into MAIL messages (`send_request`, `send_response`, `send_interrupt`, `send_broadcast`, `task_complete`).
  - Tracks pending requests keyed by `task_id`; resolves only on `broadcast_complete`.
  - Supports continuous operation and graceful shutdown (waits for active tasks to finish).
- Actions:
  - Non-MAIL domain actions SHOULD emit action result broadcasts to inform interested agents.
- Concurrency:
  - Implementations SHOULD process asynchronously while preserving priority ordering semantics.

## REST Transport

Authoritative contract: `spec/openapi.yaml`.

### Security

- HTTP Bearer authentication.
- Roles:
  - `user|admin`: initiate user chats and interswarm sends.
  - `agent`: call interswarm receive/response endpoints.

### Endpoints (summary)

- `GET /`: Health probe. Returns `{ name, status, version }`.
- `GET /status` (bearer): Server status, including swarm and user-instance indicators.
- `POST /chat` (user|admin): Body `{ message: string }`. Creates a MAIL request to `supervisor` and returns final `response.body` when `broadcast_complete` resolves.
- `GET /swarms`: List known swarms from registry.
- `POST /swarms/register` (admin): `{ name, base_url, auth_token?, volatile?, metadata? }`. Registers/updates remote swarm. Non-volatile entries persist.
- `POST /interswarm/message` (agent): Body is `MAILInterswarmMessage`. Delivers wrapped payload into local MAIL; returns a `MAILMessage` response (for request/response flows).
- `POST /interswarm/response` (agent): Body is `MAILMessage`. Submits a response from a remote swarm to the origin’s MAIL pipeline; returns `{ status, task_id }`.

## Swarm Registry

- Purpose: Service discovery, endpoint metadata, and health checks.
- Endpoint model fields: `swarm_name`, `base_url`, `health_check_url`, `auth_token_ref`, `last_seen`, `is_active`, `metadata`, `volatile`.
- Persistence: Non-volatile endpoints MUST be persisted and reloaded on startup. Persistent auth tokens SHOULD be stored as environment variable references and resolved at runtime.
- Health: Registries SHOULD perform periodic health checks; inactive endpoints are marked and MAY be skipped for routing.
- Discovery: Implementations MAY discover swarms via known discovery URLs and register found endpoints.

## Authentication and Authorization

- Bearer tokens are required for protected endpoints.
- Tokens SHOULD encode role and identity; systems MAY derive `user_id` or `agent_id` from token info to isolate MAIL instances.
- For interswarm requests, the registry MAY attach per-swarm auth tokens in the `Authorization` header.

## Error Handling

- Router errors SHOULD be returned as `MAILMessage` with `msg_type = response` and `subject = "Router Error"`.
- Unknown recipients and inactive swarms SHOULD be logged; callers MAY receive a router error response.

## Security Considerations

- Use TLS for all inter-swarm communication.
- Validate all incoming MAIL/Interswarm payloads against schemas prior to processing.
- Rate-limit public endpoints; protect registry mutation operations (admin role).
- Avoid embedding secrets in persisted registry; prefer environment variable references.

## Examples and Validation

- Example payloads: `spec/examples/*.json`.
- Validation helper: `python spec/validate_samples.py` validates inline and file-based samples against both schemas.

## Versioning

- Protocol version: 0.1.0 (draft).
- Backward-incompatible changes MUST bump the major version and update schema `$id`s and OpenAPI `info.version`.

