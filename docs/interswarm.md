# Interswarm Messaging

MAIL supports cross-swarm communication over HTTP. Remote addresses are written as `agent@swarm` and routed via the interswarm router and registry.

## Addressing
- **Local**: `agent`
- **Remote**: `agent@swarm`
- **Helper functions**: `parse_agent_address`, `format_agent_address` ([src/mail/core/message.py](/src/mail/core/message.py))

## Router ([src/mail/net/router.py](/src/mail/net/router.py))
- Detects remote recipients and wraps messages into `MAILInterswarmMessage`
- Uses the registry to find the remote base URL and resolves auth tokens from `${SWARM_AUTH_TOKEN_<NAME>}` when present
- Falls back to the message payload's `auth_token` when the registry entry does not supply one, and raises an explicit error if neither source is available
- Sends new tasks to the remote server via `/interswarm/forward` and returns follow-up or completion traffic through `/interswarm/back`
- When a local user/admin proxies a task, `post_interswarm_user_message` targets the remote `/interswarm/message` endpoint and returns the resulting `MAILMessage`

### Authentication
- Persistent registry entries store a reference to `${SWARM_AUTH_TOKEN_<SWARM>}`. Export these before starting each server so forwarded calls carry a valid bearer token.
- For volatile or ad-hoc registrations you can still embed an `auth_token` on each message; the router now uses this as a fallback.
- If both the registry and the payload omit a token, the router fails fast with `authentication token missing for swarm '<name>'` so issues surface locally rather than as a remote 401.

## Registry ([src/mail/net/registry.py](/src/mail/net/registry.py))
- Tracks local and remote swarms, performs health checks, persists non-volatile entries
- Auth tokens for persistent swarms are converted to environment variable references `${SWARM_AUTH_TOKEN_<NAME>}`
- Validates whether required env vars are set and resolves them at runtime

## Server endpoints ([src/mail/server.py](/src/mail/server.py))
- **POST `/interswarm/forward`** (agent): remote swarms send initial messages for a new or resumed task; body `{ "message": MAILInterswarmMessage }`
- **POST `/interswarm/back`** (agent): remote swarms send follow-up or completion payloads for an existing task; body `{ "message": MAILInterswarmMessage }`
- **POST `/interswarm/message`** (admin/user): local callers proxy a task to a remote swarm; body `{ user_token, body, targets, ... }`

## Enabling interswarm
- Ensure `mail.toml` (or CLI flags like `--swarm-name`, `--swarm-source`, `--swarm-registry`) identifies this server instance. The base URL is derived from `host` + `port`.
- Ensure your persistent swarm template enables interswarm where needed (see agents & supervisor tools)
- Export `SWARM_AUTH_TOKEN_<REMOTE>` for every persistent remote entry before starting the server (the registry logs a warning if the variable is missing).
- Start two servers on different ports; register them with each other using `/swarms` endpoints

## Example flow
1. User calls `POST /message` locally
2. (optional) If the entrypoint agent is not interswarm-enabled, forward the user's message to one that it
3. Interswarm-enabled agent sends a message to `target@remote-swarm` using otherwise-equal MAIL syntax
4. Router wraps the message and POSTs to the remote `/interswarm/forward`
5. Remote swarm processes the task; whenever it has a response or needs to resume locally it POSTs `/interswarm/back` to the origin swarm
6. Local server correlates each `/back` payload to the user’s original task and feeds it into the local runtime
7. Local swarm calls `task_complete` once a `broadcast_complete` arrives through the `/back` channel

## Runtime behavior
- Local agents still need explicit `comm_targets` to message peers in the same swarm, even when the address includes `@<local-swarm>`.
- `comm_targets` are enforced for local agents (including `agent@swarm` targets). Messages originating from remote swarms bypass local `comm_targets` checks.
