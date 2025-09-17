# Quickstart

This guide gets you running a local MAIL swarm and interacting with it.

Prerequisites
- Python 3.12+
- uv (recommended) or pip
- An auth service providing `AUTH_ENDPOINT` and `TOKEN_INFO_ENDPOINT` or a stub for local testing
- An LLM proxy compatible with LiteLLM (e.g., litellm) if you want tool‑driven behavior

Install
- Clone the repo and install deps:
  - `uv sync`
  - or `pip install -e .`

Environment
- Minimum environment variables:
  - `AUTH_ENDPOINT`, `TOKEN_INFO_ENDPOINT` for auth (see configuration.md)
  - `LITELLM_PROXY_API_BASE` for LLM access via the proxy
  - Optional: `SWARM_NAME`, `BASE_URL`, `SWARM_REGISTRY_FILE`

Run
- Start the server:
  - `uv run mail`
  - or `python -m mail.server`
- Default base URL: `http://localhost:8000`

Try it
- Health/root: `curl http://localhost:8000/`
- Status (requires admin/user token): `curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/status`
- Send a message: `curl -X POST http://localhost:8000/message -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"message":"Hello"}'`
- Stream (SSE): `curl -N http://localhost:8000/message -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"message":"Stream please","stream":true}'`

Next steps
- Read architecture.md to learn how the runtime processes messages
- Check agents-and-tools.md to add or modify agents
- See interswarm.md to enable cross‑swarm communication

