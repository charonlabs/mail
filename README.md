# Multi-Agent Interface Layer (MAIL): Protocol and Swarm Reference Implementation

<p align="center">
  <img src="assets/mail.png" alt="MAIL Example Diagram" width="400"/>
</p>

A standardized protocol for enabling autonomous agents to communicate, coordinate, and collaborate across distributed systems. MAIL facilitates complex multi‑agent workflows, from simple task delegation within a single environment to sophisticated cross‑organizational agent interactions spanning multiple networks and domains.

## Multi-Agent Interface Layer

See the protocol specification in `spec/` for the normative definition of MAIL message formats and behaviors. The spec text is licensed under CC BY 4.0 (see `SPEC-LICENSE`) and covered by OWFa 1.1 for Essential Claims (see `SPEC-PATENT-LICENSE`).

## MAIL Swarm Reference Implementation

### Overview

This reference implementation demonstrates a complete MAIL‑compliant multi‑agent system built with Python and FastAPI. It showcases how autonomous AI agents can be organized into swarms, communicate using the standardized MAIL message format, and coordinate to solve complex tasks both within individual swarms and across distributed networks.

Key features:
- **Persistent swarms**: Long‑running agent swarms that maintain state and context
- **HTTP APIs**: REST endpoints for client integration and inter‑swarm messaging
- **Service discovery**: Built‑in registry with health monitoring for distributed swarms
- **Flexible agents**: Configurable agents with tools, memory, and communication targets
- **Streaming + events**: Server‑Sent Events for live streaming and optional task event logs
- **Example swarms**: Supervisor, weather, math, and cross‑swarm examples

The implementation serves as both a functional multi-agent system and a reference for building MAIL-compliant applications in various domains.

### Architecture

#### Key Components

1. **MAIL Core** (`src/mail/core.py`): The main orchestration engine that manages message queuing, agent interactions, and task execution
2. **FastAPI Server** (`src/mail/server.py`): HTTP API server providing REST endpoints for client interactions and interswarm communication
3. **Agent Swarms**: Collections of specialized AI agents that can communicate with each other
4. **Interswarm Router**: Enables communication between agents across different swarms via HTTP
5. **Swarm Registry**: Service discovery system for managing multiple swarms

#### Agent Types (examples)

- **Supervisor**: Orchestrates tasks and coordinates with other agents
- **Weather**: Provides weather‑related information and forecasts
- **Math**: Performs mathematical calculations and analysis

### Prerequisites

- Python 3.12+
- `uv` package manager (recommended) or `pip`
- LiteLLM proxy server (LLM access via `litellm`)
- Authentication server implementing login + token‑info endpoints (see below)

### Installation

With `uv`:

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd mail
   ```

2. Install dependencies using `uv`:
   ```bash
   uv sync
   ```

Or with `pip`:
```bash
pip install -e .
```

### Configuration

#### Required Environment Variables

For basic operation:
```bash
# LLM proxy (configure according to your LiteLLM deployment)
LITELLM_PROXY_API_BASE=http://your-litellm-proxy-url

# Auth service endpoints
AUTH_ENDPOINT=http://your-auth-server/auth/login
TOKEN_INFO_ENDPOINT=http://your-auth-server/auth/check

# Example provider keys used by the proxy and memory system
OPENAI_API_KEY=sk-your-openai-api-key
ANTHROPIC_API_KEY=sk-your-anthropic-api-key
```

For inter‑swarm messaging and registry:
```bash
# Swarm identification
SWARM_NAME=my-swarm-name          # Default: "default"
BASE_URL=http://localhost:8000     # Default: "http://localhost:8000"

# Optional database connection
DATABASE_URL=your-database-url     # Default: "none"

# Registry persistence file (created/used by server)
SWARM_REGISTRY_FILE=registries/example.json  # Default: registries/example.json
```

#### Swarm Configuration

The system uses a single JSON configuration file to define swarms:

- `swarms.json`: Contains all accessible swarm definitions, including configurations for both single‑swarm operation and multi‑swarm deployments.

Example swarm configuration:
```json
[
    {
        "name": "example",
        "version": "1.0.0",
        "entrypoint": "supervisor",
        "agents": [
            {
                "name": "supervisor",
                "factory": "mail.factories.supervisor:supervisor_factory",
                "llm": "openai/o3-mini",
                "system": "mail.examples.supervisor.prompts:SYSPROMPT",
                "comm_targets": ["weather", "math"],
                "agent_params": { }
            },
            {
                "name": "weather",
                "factory": "mail.examples.weather_dummy.agent:factory_weather_dummy",
                "llm": "openai/o3-mini",
                "system": "mail.examples.weather_dummy.prompts:SYSPROMPT",
                "comm_targets": ["supervisor", "math"],
                "agent_params": { 
                    "actions": [
                        {
                            "name": "get_weather_forecast",
                            "description": "Get the weather forecast for a given location",
                            "parameters": { 
                                "type": "object",
                                "properties": {
                                    "location": { "type": "string", "description": "The location to get the weather forecast for" },
                                    "days_ahead": { "type": "integer", "description": "The number of days ahead to get the weather forecast for" },
                                    "metric": { "type": "boolean", "description": "Whether to use metric units" }
                                }
                            },
                            "function": "mail.examples.weather_dummy.actions:get_weather_forecast"
                        }
                    ]
                 }
            },
            {
                "name": "math",
                "factory": "mail.examples.math_dummy.agent:factory_math_dummy",
                "llm": "openai/o3-mini",
                "system": "mail.examples.math_dummy.prompts:SYSPROMPT",
                "comm_targets": ["supervisor", "weather"],
                "agent_params": { }
            }
        ]
    }
]
```

### Running the Server

```bash
# Set environment variables
export SWARM_NAME=my-swarm
export BASE_URL=http://localhost:8000
export LITELLM_PROXY_API_BASE=http://your-litellm-proxy-url
export AUTH_ENDPOINT=http://your-auth-server/auth/login
export TOKEN_INFO_ENDPOINT=http://your-auth-server/auth/check

# Start the server
uv run mail

# Or with Python
python -m mail.server
```

The server will start on `http://localhost:8000` by default.

### API Usage

#### Authentication

All requests use a Bearer token in the `Authorization` header:
```bash
Authorization: Bearer YOUR_API_TOKEN
```

#### Basic Endpoints

- Health/root:
```bash
curl http://localhost:8000/
```

- Server status (shows active user instance state):
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/status
```

- Chat with agents (JSON body):
```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "What is the weather like today?"}'
```

Optional parameters for `/message`:
- `entrypoint`: override default entrypoint agent (e.g., `"weather"`)
- `show_events`: include task events in the response
- `stream`: stream the response via SSE

Examples:
```bash
# Specify entrypoint
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "Summarize this.", "entrypoint": "weather"}'

# Stream response (SSE)
curl -N http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "Stream a response", "stream": true}'
```

#### Interswarm Communication

- List available swarms:
```bash
curl http://localhost:8000/swarms
```

- Register a new swarm (admin token required):
```bash
curl -X POST http://localhost:8000/swarms/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "name": "remote-swarm",
    "base_url": "http://localhost:8001",
    "auth_token": "optional-token",
    "volatile": true
  }'
```

- Send inter‑swarm message:

The API expects a fully qualified `target_agent` in the form `agent@swarm` (e.g., `consultant@swarm-beta`). It also requires `user_token`, which is the internal user identifier used by the server (`{role}_{id}`). You can derive it by calling your `TOKEN_INFO_ENDPOINT` and composing `role` + `_` + `id`.

```bash
curl -X POST http://localhost:8000/interswarm/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "target_agent": "consultant@remote-swarm",
    "message": "Hello from local swarm!",
    "user_token": "user_12345"
  }'
```

### Multi‑Swarm Deployment

To set up multiple communicating swarms:

#### Terminal 1: Start First Swarm
```bash
export SWARM_NAME=swarm-alpha
export BASE_URL=http://localhost:8000
export LITELLM_PROXY_API_BASE=http://your-litellm-proxy-url
export AUTH_ENDPOINT=http://your-auth-server/auth/login
export TOKEN_INFO_ENDPOINT=http://your-auth-server/auth/check
uv run mail
```

#### Terminal 2: Start Second Swarm
```bash
export SWARM_NAME=swarm-beta
export BASE_URL=http://localhost:8001
export LITELLM_PROXY_API_BASE=http://your-litellm-proxy-url
export AUTH_ENDPOINT=http://your-auth-server/auth/login
export TOKEN_INFO_ENDPOINT=http://your-auth-server/auth/check
uv run mail
```

#### Register Swarms with Each Other (admin token required)
```bash
# Register swarm-beta with swarm-alpha
curl -X POST http://localhost:8000/swarms/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"name": "swarm-beta", "base_url": "http://localhost:8001"}'

# Register swarm-alpha with swarm-beta
curl -X POST http://localhost:8001/swarms/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"name": "swarm-alpha", "base_url": "http://localhost:8000"}'
```

### Development

#### Project Structure
```
mail/
├── src/mail/
│   ├── core.py              # MAIL orchestration engine
│   ├── server.py            # FastAPI server with inter‑swarm support + SSE
│   ├── server_simple.py     # Minimal server for testing
│   ├── auth.py              # Auth integration (login + token info)
│   ├── message.py           # Message types + helpers
│   ├── executor.py          # Action execution engine
│   ├── interswarm_router.py # Inter‑swarm message routing
│   ├── swarm_registry.py    # Service discovery + health checks
│   ├── factories/           # Agent factory functions
│   ├── examples/            # Example agents and prompts
│   └── swarms/              # Swarm management utilities
├── swarms.json              # Swarm definitions and configuration
├── registries/              # Saved registry state (paths in env)
└── pyproject.toml           # Project metadata + deps
```

#### Adding New Agents

1. Create agent implementation in `src/mail/examples/your_agent/`
2. Add agent configuration to `swarms.json`
3. Implement required factory function and prompts
4. Restart the server

### Authentication Setup

The system requires a separate server for authentication. Specifically, the endpoints you need are as follows:

1. `AUTH_ENDPOINT`: Accepts an `Authorization: Bearer` header containing a swarm API key and returns a temporary token for the caller (user/agent) in the following format:
```json
{
  "token": "string"
}
```
2. `TOKEN_INFO_ENDPOINT`: Accepts an `Authorization: Bearer` header containing a temporary token and returns info for the caller in the following format:
```json
{
  "role": "admin" | "user" | "agent",
  "id": "string",
  "api_key": "string"
}
```

The server derives an internal `user_token` as `{role}_{id}`. When calling `/interswarm/send`, provide this value in the `user_token` field (or let agents initiate inter‑swarm messages via tools during a normal `/message` conversation).

### Troubleshooting

#### Common Issues

1. **Server won't start**: Verify required environment variables and LiteLLM proxy configuration
2. **Authentication errors**: Ensure your API token is valid and auth endpoints are reachable
3. **Agent communication failures**: Check `swarms.json` for correct factory/system import paths (`mail...`) and agent names
4. **Inter‑swarm issues**: Confirm swarms are registered (admin token), health checks passing, and targets use `agent@swarm` format

#### Logs

The system uses Python logging. Enable debug logging to see detailed message flow:
```bash
export PYTHONPATH=src
python -c "import logging; logging.basicConfig(level=logging.DEBUG)"
```

### Security Considerations

- Use HTTPS in production deployments
- Require admin tokens for registry mutations (`/swarms/register`, `/swarms/load`)
- Use separate tokens/roles for users vs. agents
- Consider rate limiting for public‑facing endpoints
- Validate/limit tool execution and uploaded content
- Use secure networks for swarm‑to‑swarm communication

### Contributing

We welcome contributions to both the protocol spec and the reference implementation.

- Start with `CONTRIBUTING.md` for the workflow and guidelines.
- All commits must include a DCO sign‑off (`git commit -s`). See `DCO`.
- Open an issue to discuss significant changes before starting work.

### License

- Code: Licensed under Apache License 2.0. See `LICENSE`.
- Specification text: Licensed under Creative Commons Attribution 4.0 (CC BY 4.0). See `SPEC-LICENSE`.
- Specification patent license: Open Web Foundation Final Specification Agreement 1.1 (OWFa 1.1). See `SPEC-PATENT-LICENSE`.
- Trademarks: See `TRADEMARKS.md` for descriptive use policy.

Using the spec or code implies acceptance of their respective licenses.

### Additional Resources

- Inter‑swarm messaging overview: `docs/INTERSWARM_README.md`
- Registry configuration: `docs/swarm_registry_config.md`
- Registry security notes: `docs/swarm_registry_security.md`
- Auth reference implementation notes: `docs/AUTH_TOKEN_REF_IMPLEMENTATION.md`
- Agent examples: `src/mail/examples/`
- Agent factories: `src/mail/factories/`

### Development

- Run server locally: `uv run mail` or `python -m mail.server`
- Run tests: `uv run pytest -q`
- Lint/format: `uv run ruff check --fix .`
