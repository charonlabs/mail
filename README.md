# Multi-Agent Interface Layer (MAIL)

[![PyPI](https://img.shields.io/pypi/v/mail-swarms)](https://pypi.org/project/mail-swarms/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Spec](https://img.shields.io/badge/MAIL%20spec-v2.0-blueviolet)](spec/SPEC.md)

**MAIL is an open protocol — and a Python implementation — for email-like
communication between humans and AI agents.** Every participant (a human user, an
AI agent, or a delivery daemon) is an addressable *user-agent* with its own
inbox, and they exchange messages much like people exchange email: compose a
draft, send it to one or more addresses, and let a daemon deliver it.

MAIL deliberately covers the **communication layer and little else** — not an
agent runtime, not tool execution. If you already have agents, MAIL gives them a
shared, standard way to talk. See [What is MAIL?](docs/explanations/mail-v2-overview.md).

## Highlights

- **Email-like model** — addresses, inboxes, outboxes, drafts, trash, and
  mailing lists, all defined by an open [specification](spec/SPEC.md).
- **HTTP-native** — a FastAPI server with an authoritative
  [OpenAPI contract](spec/openapi.yaml); any client that speaks the contract works.
- **Separation of concerns** — the server owns state, daemons deliver messages,
  clients are just authenticated user-agents.
- **Pluggable storage** — an in-memory backend for development and a
  transactional SQLite backend for durability.
- **Batteries included** — a CLI client (`mail`), an admin CLI (`mail-admin`), a
  delivery daemon, and webhook delivery for push notifications.

## Installation

MAIL ships as five lockstep packages on PyPI under `mail-swarms-*`. Install the
components you need:

```bash
pip install mail-swarms-server   # the FastAPI server + backend-init
pip install mail-swarms-client   # the `mail` and `mail-admin` CLIs
pip install mail-swarms-daemon   # the delivery daemon
```

To work from a source checkout, use [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/charonlabs/mail.git
cd mail
uv sync
```

Requires Python 3.12+.

## Quickstart

Bring up a local deployment and send your first message. (Prefix commands with
`uv run` when working from a source checkout.)

```bash
# 1. Initialize a local memory backend (creates a swarm + starter user-agents)
uv run backend-init --type memory --host localhost

# 2. Configure and start the server
export MAIL_HOST=localhost
export MAIL_JWT_SECRET_KEY=$(openssl rand -hex 32)
export MAIL_JWT_ALGORITHM=HS256
export MAIL_JWT_EXPIRE_MINUTES=30
export MAIL_REFRESH_TOKEN_EXPIRE_DAYS=30
uv run mail-server --backend memory          # http://127.0.0.1:8865

# 3. In another terminal, start the delivery daemon (with daemon credentials)
uv run mail-daemon

# 4. In a third terminal, log in and send a message
export MAIL_SERVER=http://127.0.0.1:8865
uv run mail login
uv run mail compose "Hello" "My first MAIL message"
uv run mail send <draft_id> supervisor@default@localhost
```

The full walkthrough — including where the generated credentials live — is in
[Run MAIL Locally](docs/tutorials/run-local-mail.md).

## Packages

| Package | Directory | Provides |
| --- | --- | --- |
| [`mail-swarms-protocol`](https://pypi.org/project/mail-swarms-protocol/) | `src/mail/protocol` | Shared protocol types, constants, and validators |
| [`mail-swarms-server`](https://pypi.org/project/mail-swarms-server/) | `src/mail/server` | FastAPI server, storage backends, `backend-init` |
| [`mail-swarms-client`](https://pypi.org/project/mail-swarms-client/) | `src/mail/client` | `mail` and `mail-admin` CLIs |
| [`mail-swarms-daemon`](https://pypi.org/project/mail-swarms-daemon/) | `src/mail/daemon` | The delivery daemon (`mail-daemon`) |

## Documentation

Full docs live in [`docs/`](docs/README.md), organized by the
[Divio system](docs/explanations/documentation-system.md):

- **Tutorials** — [Run MAIL Locally](docs/tutorials/run-local-mail.md) ·
  [Send Your First Message](docs/tutorials/send-first-message.md) ·
  [Build a Minimal HTTP Client](docs/tutorials/build-minimal-http-client.md) ·
  [Build a Webhook Receiver](docs/tutorials/build-webhook-receiver.md)
- **How-to guides** — [running the server](docs/howtos/run-server.md),
  [daemon](docs/howtos/run-daemon.md), [authentication](docs/howtos/authenticate-user-agent.md),
  [sending messages](docs/howtos/send-message-cli.md),
  [swarms](docs/howtos/manage-swarms.md),
  [mailing lists](docs/howtos/manage-mailing-lists.md),
  [webhooks](docs/howtos/manage-webhooks.md), and more.
- **Reference** — [HTTP API](docs/references/http-api.md) ·
  [Data Models](docs/references/data-models.md) ·
  [Configuration](docs/references/configuration.md) ·
  [Storage Backends](docs/references/storage-backends.md) ·
  [CLIs](docs/references/client-cli.md)
- **Explanations** — [Architecture](docs/explanations/architecture.md) ·
  [Addressing](docs/explanations/addressing-model.md) ·
  [Delivery](docs/explanations/delivery-model.md) ·
  [Security](docs/explanations/security-model.md)

The protocol itself is specified in [`spec/SPEC.md`](spec/SPEC.md), with the
authoritative HTTP contract in [`spec/openapi.yaml`](spec/openapi.yaml).

## Repository layout

```text
mail/
├── docs/              # documentation (tutorials / howtos / references / explanations)
├── spec/              # SPEC.md + generated openapi.yaml
├── src/mail/
│   ├── protocol/      # mail-swarms-protocol
│   ├── server/        # mail-swarms-server
│   ├── client/        # mail-swarms-client
│   ├── daemon/        # mail-swarms-daemon
│   └── legacy/        # archived MAIL v1 runtime (reference only)
├── tests/             # active v2 test suite (contract / e2e / integration / unit)
├── scripts/           # artifact generation + maintenance
└── pyproject.toml     # uv workspace + meta-package
```

See [Repository Layout](docs/references/repository-layout.md) for the full map.

## Development

```bash
uv sync              # install the workspace
uv run pytest        # run the active v2 test suite
uv run mail --help   # explore the client CLI
```

More: [Run the Test Suite](docs/howtos/run-tests.md) ·
[Regenerate API Artifacts](docs/howtos/regenerate-api-artifacts.md).

The MAIL v1 runtime is archived under `src/mail/legacy/` for reference and is not
part of the v2 packages — see [MAIL v1 Legacy Runtime](docs/explanations/mail-v1-legacy.md).

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md); commits
must be signed off under the [Developer Certificate of Origin](DCO).

## License

Reference implementation code is licensed under the
[Apache License 2.0](LICENSE). The protocol specification and patent grant are
covered by [SPEC-LICENSE](SPEC-LICENSE) and
[SPEC-PATENT-LICENSE](SPEC-PATENT-LICENSE). "MAIL" and related marks are subject
to the [trademark policy](TRADEMARKS.md).
