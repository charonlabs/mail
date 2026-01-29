# Quickstart

This guide gets you running a local MAIL swarm and interacting with it.

## Prerequisites
- **Python 3.12+**
- **uv** (recommended) or **pip**
- An **auth service** providing `AUTH_ENDPOINT` and `TOKEN_INFO_ENDPOINT` or a stub for local testing
- An **LLM proxy** compatible with LiteLLM (e.g., `litellm`) only if your swarm uses `use_proxy=true`

## Install

### Cloning the repo
```bash
git clone https://github.com/charonlabs/mail.git \
--branch v1.3.2
```

### Installing dependencies
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

## Environment & Config
- Start with `mail.toml` (checked into the repo) to control default host, port, swarm source, client timeout, and `[server.settings.task_message_limit]`. Copy it if you need environment-specific values and point `MAIL_CONFIG_PATH` (or `--config`) at the new file.
- Minimum environment variables:
  - `AUTH_ENDPOINT`, `TOKEN_INFO_ENDPOINT` for auth (see [configuration.md](/docs/configuration.md))
  - `LITELLM_PROXY_API_BASE` for LLM access only when `use_proxy=true`
  - Optional: `DATABASE_URL` for PostgreSQL persistence of agent histories and task state (see [database.md](/docs/database.md))

## Run
- Start the server:
```bash
# Using uv (recommended)
uv run mail server

# Or
python -m mail.server
```
- Default base URL comes from `mail.toml` (`host` + `port`); override per run with CLI flags or by editing the file / `MAIL_CONFIG_PATH`.
- Need the OpenAI Responses bridge for integration testing? Start the server with `uv run mail server --debug` (or set `[server].debug = true`) to expose the debug-only `/responses` endpoint.
- Prefer containers? Follow the [Docker deployment guide](./docker.md) to build and run the same server with Docker or Compose.

## Try it
- **Check connectivity**:
```bash
# Quick health check using the CLI
uv run mail ping http://localhost:8000
```
- **Basic server info**:
```bash
# Get the swarm name, status, and protocol version
curl http://localhost:8000/

# Get the swarm name and more detailed health status
curl http://localhost:8000/health
```
- **Status** (requires admin/user token): 
```bash
curl -H "Authorization: Bearer $TOKEN" \
http://localhost:8000/status
```
- **MAIL CLI REPL** (enter `help` for commands): 
```bash
uv run mail client \
http://localhost:8000 \
--api-key $TOKEN
``` 
- **Debug `/responses` (optional)**: 
```bash
uv run mail client http://localhost:8000 --api-key $TOKEN
mail> responses '[{"role":"user","content":"Plan tomorrow"}]' '[]' \
      --instructions "You are a helpful planner."
```
- **Send a message**: 
```bash
curl -X POST http://localhost:8000/message \
-H "Content-Type: application/json" \
-H "Authorization: Bearer $TOKEN" \
-d '{"body":"Hello"}'
```
- **Stream (SSE)**: 
```bash
curl -N -X POST http://localhost:8000/message \
-H "Content-Type: application/json" \
-H "Authorization: Bearer $TOKEN" \
-d '{"body":"Stream please","stream":true}'
```
- **Python client**: use [`MAILClient`](./client.md) if you prefer asyncio code over raw HTTP. Example:
```python
import asyncio
import os
from mail.client import MAILClient

async def main() -> None:
    token = os.getenv("TOKEN")
    async with MAILClient("http://localhost:8000", api_key=token) as client:
        print(await client.ping())
        print(await client.post_message("Hello from Python"))

asyncio.run(main())
```

## Next steps
- Read [architecture.md](/docs/architecture.md) to learn how the runtime processes messages
- Check [agents-and-tools.md](/docs/agents-and-tools.md) to learm how to add or modify agents
- See [interswarm.md](/docs/interswarm.md) to enable cross‑swarm communication
