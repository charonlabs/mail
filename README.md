# Multi-Agent Interface Layer (MAIL)

Single-swarm example | Multi-swarm example
:-------------------:|:-------------------:
![](/assets/mail.png)| ![](/assets/interswarm.png)

**MAIL** is an **open protocol** for letting autonomous agents communicate, coordinate, and cooperate across local runtimes and distributed swarms. This repository hosts both the normative specification and a production-grade **Python/FastAPI reference implementation** that demonstrate how to build interoperable agent systems on top of the MAIL contract.

---

## Quick Links
- **Protocol specification**: [spec/SPEC.md](/spec/SPEC.md)
- **JSON Schemas**: [spec/MAIL-core.schema.json](/spec/MAIL-core.schema.json), [spec/MAIL-interswarm.schema.json](/spec/MAIL-interswarm.schema.json)
- **REST transport** (OpenAPI 3.1): [spec/openapi.yaml](/spec/openapi.yaml)
- **Reference implementation source**: [src/mail/](/src/mail/__init__.py)
- **Deployment examples and docs**: [docs/](/docs/README.md)

## 1. MAIL Protocol Overview

### Goals
- Provide a transport-agnostic **message contract** so agents from different vendors can interoperate.
- Encode **routing, addressing, and task lifecycle semantics** that work for single-swarm and cross-swarm topologies.
- Support reliable inter-swarm federation over **standard HTTP** infrastructure.
- Remain **minimal enough** to embed inside bespoke agent runtimes or platform orchestrators.

### Message Primitives
MAIL defines five core message types that all conforming systems MUST understand. Each payload is validated against `MAIL-core.schema.json`.

| `msg_type`           | Required payload fields                                                                 | Typical use case                                  |
|----------------------|-------------------------------------------------------------------------------------------|---------------------------------------------------|
| `request`            | `task_id`, `request_id`, `sender`, `recipient`, `subject`, `body`                        | Agent-to-agent task delegation                    |
| `response`           | `task_id`, `request_id`, `sender`, `recipient`, `subject`, `body`                        | Reply that correlates with a prior request        |
| `broadcast`          | `task_id`, `broadcast_id`, `sender`, `recipients[]`, `subject`, `body`                   | Notify many agents in a swarm                     |
| `interrupt`          | `task_id`, `interrupt_id`, `sender`, `recipients[]`, `subject`, `body`                   | High-priority stop/alter instructions             |
| `broadcast_complete` | `id`, `timestamp`, `message.broadcast_id`, plus broadcast payload                        | Marks task completion by a supervisor agent       |

All messages are wrapped in a `MAILMessage` envelope with an `id` (UUID) and RFC 3339 timestamp. Optional fields such as `sender_swarm`, `recipient_swarm`, and `routing_info` carry federation metadata without altering the core contract.

### Addressing & Routing
- **Local agents** are addressed by name (`agent-name`).
- **Interswarm addresses** append the remote swarm (`agent-name@swarm-name`).
- **Routers** MUST wrap cross-swarm traffic in a `MAILInterswarmMessage` that includes source/target swarm identifiers and optional metadata.
- **Priority tiers** ensure urgent system and user messages preempt regular agent chatter. Within a tier, messages are FIFO by timestamp.

### Transport Requirements
- The **normative HTTP binding** is published in [spec/openapi.yaml](/spec/openapi.yaml) and implemented by the reference **FastAPI** service.
- **`/message`** handles user tasks and local agent traffic. **`/interswarm/message`** federates swarms.
- Implementations MUST replay responses from remote swarms back into the local queue to complete task lifecycles.

### Conformance & Validation
- Use the **included JSON Schemas** for request/response validation in any runtime.
- Run **`uv run spec/validate_samples.py`** to check sample payloads against the schemas.
- Terms defined in the spec follow RFC 2119/RFC 8174 keywords.

## 2. Reference Implementation

### Key Features
- **Persistent swarm runtime** with pluggable agents, tools, and memory backends.
- **FastAPI HTTP server** exposing REST endpoints, **Server-Sent Events (SSE)** streams, and **interswarm messaging** routes.
- Built-in **swarm registry** with **health checks** and **service discovery** for distributed deployments.
- **Configurable authentication layer** that plugs into external auth/token providers.
- **Example agents** (`supervisor`, `weather`, `math`, cross-swarm demos) showcasing MAIL usage patterns.

### Architecture Highlights
- **[src/mail/core/runtime.py](/src/mail/core/runtime.py)**: Mailbox scheduling, task orchestration, priority queues, and tool execution.
- **[src/mail/server.py](/src/mail/server.py)**: FastAPI application with REST + SSE endpoints and interswarm routing.
- **[src/mail/net/router.py](/src/mail/net/router.py)**: HTTP federation between swarms, including metadata rewriting.
- **[src/mail/net/registry.py](/src/mail/net/registry.py)**: Service registry and liveness monitoring for remote swarms.
- **[src/mail/factories/](/src/mail/factories/__init__.py)**: Factory functions that instantiate agents with their LLM/tool configuration.
- **[src/mail/examples/](/src/mail/examples/__init__.py)**: Example agents and prompts.

The runtime processes MAIL messages **asynchronously**, tracks per-task state, and produces `broadcast_complete` events to signal overall task completion.

## 3. Getting Started

### Prerequisites
- **Python 3.12+**
- [`uv`](https://github.com/astral-sh/uv) package manager (recommended) or `pip`
- **[LiteLLM](https://github.com/BerriAI/litellm) proxy endpoint** for LLM calls
- **Authentication service** providing `/auth/login` and `/auth/check` (see below)

### Installation
```bash
# Clone and enter the repository
git clone https://github.com/charonlabs/mail
cd mail

# Install dependencies (preferred)
uv sync

# or, using pip
pip install -e .
```

### Configuration
Set the following **environment variables** before starting the server:

```bash
# LLM proxy
export LITELLM_PROXY_API_BASE=http://your-litellm-proxy

# Authentication endpoints
export AUTH_ENDPOINT=http://your-auth-server/auth/login
export TOKEN_INFO_ENDPOINT=http://your-auth-server/auth/check

# Optional provider keys consumed by the proxy
export OPENAI_API_KEY=sk-your-openai-api-key
export ANTHROPIC_API_KEY=sk-your-anthropic-key

# Swarm identity & networking
export SWARM_NAME=my-swarm            # default: "default"
export BASE_URL=http://localhost:8000
export SWARM_REGISTRY_FILE=registries/example.json
# Optional persistence (set to "none" to disable)
export DATABASE_URL=postgresql://...
```

**Swarm definitions** live in [swarms.json](/swarms.json). Each entry declares the agents, entrypoint, tools, and default models for a swarm.

### Run a Local Swarm
```bash
# Start the FastAPI server (includes SSE + registry)
uv run mail
# or explicitly
uv run -m mail.server
```

### Federate Two Swarms (Example)
```bash
# Terminal 1
BASE_URL=http://localhost:8000 SWARM_NAME=swarm-alpha uv run mail

# Terminal 2
BASE_URL=http://localhost:8001 SWARM_NAME=swarm-beta uv run mail

# Register each swarm with the other (requires admin bearer token)
curl -X POST http://localhost:8000/swarms/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "swarm-beta", "base_url": "http://localhost:8001"}'

curl -X POST http://localhost:8001/swarms/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "swarm-alpha", "base_url": "http://localhost:8000"}'
```
Agents can now address peers using `agent-name@swarm-name`, and responses will route back automatically.

## 4. Repository Layout
```
mail/
├── spec/                  # Protocol specification, schemas, validation utilities
├── src/mail/              # Reference implementation (core runtime + FastAPI services)
├── docs/                  # Supplemental docs (registry, inter-swarm, auth, etc.)
├── swarms.json            # Default swarm configurations
├── tests/                 # Pytest suite covering protocol + runtime behaviors
├── scripts/               # Operational helpers (deploy, smoke tests, tooling)
├── registries/            # Sample registry persistence outputs
├── assets/                # Diagrams and static assets (README image, etc.)
└── pyproject.toml         # Project metadata and dependency definitions
```

## 5. Development Workflow
- **`uv run mail`** – run the reference server locally.
- **`uv run pytest -q`** – execute the automated test suite.
- **`uv run ruff check --fix .`** – lint and auto-fix style issues.
- **`uv run spec/validate_samples.py`** – validate example MAIL payloads against the schemas.

## 6. Documentation & Resources
- **Quickstart guide**: [docs/quickstart.md](/docs/quickstart.md)
- **Architecture deep-dive**: [docs/architecture.md](/docs/architecture.md)
- **Protocol message format reference**: [docs/message-format.md](/docs/message-format.md)
- **HTTP/API surface**: [docs/api.md](/docs/api.md)
- **Swarm configuration & registry operations**: [docs/configuration.md](/docs/configuration.md), [docs/registry.md](/docs/registry.md)
- **Security hardening checklist**: [docs/security.md](/docs/security.md)
- **Agents, tools, and examples**: [docs/agents-and-tools.md](/docs/agents-and-tools.md), [docs/examples.md](/docs/examples.md)
- **Testing and troubleshooting**: [docs/testing.md](/docs/testing.md), [docs/troubleshooting.md](/docs/troubleshooting.md)
- **Runtime source directories**: [src/mail/examples/](/src/mail/examples/__init__.py), [src/mail/factories/](/src/mail/factories/__init__.py)

## 7. Contributing
- **Read [CONTRIBUTING.md](/CONTRIBUTING.md)** for branching, issue, and review guidelines.
- All commits require a **Developer Certificate of Origin sign-off** (`git commit -s`).
- Please open an issue to propose significant protocol changes before implementation.
- Core maintainers are listed in [MAINTAINERS.md](/MAINTAINERS.md).

## 8. Licensing & Trademarks
- Reference implementation code: **Apache License 2.0** ([LICENSE](/LICENSE)).
- Specification text: **Creative Commons Attribution 4.0** ([SPEC-LICENSE](/SPEC-LICENSE)).
- Essential patent claims: **Open Web Foundation Final Specification Agreement 1.0** ([SPEC-PATENT-LICENSE](/SPEC-PATENT-LICENSE)).
- Trademarks and descriptive use policy: [TRADEMARKS.md](/TRADEMARKS.md).

Using the spec or code implies acceptance of their respective terms.

---

For questions, bug reports, or feature requests, open an issue or start a discussion in this repository.
