# HTTP API

The server exposes a **FastAPI application** ([src/mail/server.py](/src/mail/server.py)) with endpoints for user messaging, interswarm routing, and registry management. An **OpenAPI description** also exists in [spec/openapi.yaml](/spec/openapi.yaml).

## Auth
- All non-root endpoints require `Authorization: Bearer <token>`
- The server validates tokens via `TOKEN_INFO_ENDPOINT`, expecting `{ role, id, api_key }`
- Roles: `admin`, `user`, `agent`
- See [src/mail/utils/auth.py](/src/mail/utils/auth.py) for more info

## Endpoints
- **GET `/`** → basic info with name/version/status
- **GET `/status`** (admin/user) → readiness and active user instance check
- **POST `/message`** (admin/user)
  - **Body**: `{ message: string, entrypoint?: string, show_events?: bool, stream?: bool }`
  - **Behavior**: enqueues a user-scoped request to the default or explicit entrypoint
  - **Streaming**: when `stream: true`, returns SSE stream until completion
- **POST `/interswarm/message`** (agent)
  - Accepts a MAILInterswarmMessage from a remote swarm, returns a MAILMessage response
- **POST `/interswarm/response`** (agent)
  - Accepts a MAILMessage response from a remote swarm and routes it to the matching local task
- **POST `/interswarm/send`** (admin/user)
  - **Body**: `{ target_agent: "agent@remote-swarm", message: string, user_token: string }`
  - Sends a direct interswarm request via the local user’s runtime/router
- **GET `/swarms`** → lists known swarms from the local registry
- **POST `/swarms`** (admin) → registers a swarm in the registry (volatile by default)
- **GET `/swarms/dump`** (admin) → dumps current registry as JSON
- **POST `/swarms/load`** (admin) → loads a new persistent MAILSwarmTemplate from JSON

## SSE streaming
- **POST `/message`** with `stream: true` yields `text/event-stream`
- **Events** include periodic `ping` heartbeats and a final `task_complete` with the response body

## Error handling
- Standard FastAPI HTTP errors with detail strings; runtime also produces structured system responses when routing fails

## Notes
- The server maintains a persistent `MAILSwarmTemplate` and per-user `MAILSwarm` instances
- Interswarm endpoints are restricted to callers with the `agent` role
- For message shapes and schemas, see [message-format.md](/docs/message-format.md) and [spec/](/spec/SPEC.md)

