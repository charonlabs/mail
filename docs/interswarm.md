# Interswarm Messaging

MAIL supports cross-swarm communication over HTTP. Remote addresses are written as `agent@swarm` and routed via the interswarm router and registry.

## Addressing
- **Local**: `agent`
- **Remote**: `agent@swarm`
- **Helpers**: `parse_agent_address`, `format_agent_address` ([src/mail/core/message.py](/src/mail/core/message.py))

## Router ([src/mail/net/router.py](/src/mail/net/router.py))
- Detects remote recipients and wraps messages into `MAILInterswarmMessage`
- Uses the registry to find the remote base URL and (optional) resolved auth token
- Sends to the remote server `/interswarm/message`; returns a `MAILMessage`
- Incoming responses from remotes can be injected via `/interswarm/response`

## Registry ([src/mail/net/registry.py](/src/mail/net/registry.py))
- Tracks local and remote swarms, performs health checks, persists non-volatile entries
- Auth tokens for persistent swarms are converted to environment variable references `${SWARM_AUTH_TOKEN_<NAME>}`
- Validates whether required env vars are set and resolves them at runtime

## Server endpoints ([src/mail/server.py](/src/mail/server.py))
- **POST `/interswarm/message`** (agent): remote swarms call this with a `MAILInterswarmMessage`
- **POST `/interswarm/response`** (agent): remote swarms can return a direct `MAILMessage` response
- **POST `/interswarm/send`** (admin/user): convenience endpoint to send to `agent@remote-swarm` via a local user instance

## Enabling interswarm
- Provide `SWARM_NAME`, `BASE_URL`, and a `SWARM_REGISTRY_FILE`
- Ensure your persistent swarm template enables interswarm where needed (see agents & supervisor tools)
- Start two servers on different ports; register them with each other using `/swarms` endpoints

## Example flow
1. User calls `POST /message` locally
2. Supervisor sends a tool call to `target@remote-swarm`
3. Router wraps the message and POSTs to the remote `POST /interswarm/message`
4. Remote swarm processes and returns a `MAILMessage` response
5. Local server correlates and completes the user’s task

