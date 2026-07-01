# Repository Layout

Status: draft

This page maps the MAIL repository so you can find the code, specification, and
tests behind everything else in these docs. MAIL v2 is a [uv][uv] workspace: a
root meta-package plus four member packages under `src/mail/`, with the archived
v1 runtime kept alongside them.

## Top level

```text
mail/
├── docs/                    # this documentation set (tutorials/howtos/references/explanations)
├── spec/                    # protocol source of truth: SPEC.md + openapi.yaml
├── src/mail/                # the workspace packages (see below)
├── tests/                   # active v2 test suite (contract/e2e/integration/unit)
├── scripts/                 # repository maintenance + artifact generation
├── pyproject.toml           # uv workspace + root meta-package + shared tooling config
├── pytest.ini               # test configuration
├── uv.lock                  # locked dependency graph for the whole workspace
├── llms.txt                 # generated LLM-oriented API digest
├── README.md                # repository overview
├── SPEC-LICENSE, SPEC-PATENT-LICENSE, LICENSE, NOTICE, TRADEMARKS.md, DCO
└── THIRD_PARTY_NOTICES.md   # generated third-party license aggregation
```

## Workspace packages

Each package lives at `src/mail/<pkg>/` with its own `pyproject.toml`,
`README.md`, and a `src/mail_<pkg>/` import root. All four are published to PyPI
in lockstep under the `mail-swarms-*` names.

| Directory | Package name | Import root | Console scripts |
| --- | --- | --- | --- |
| `src/mail/protocol/` | `mail-swarms-protocol` | `mail_protocol` | `mail-protocol` |
| `src/mail/server/` | `mail-swarms-server` | `mail_server` | `mail-server`, `backend-init` |
| `src/mail/client/` | `mail-swarms-client` | `mail_client` | `mail`, `mail-admin` |
| `src/mail/daemon/` | `mail-swarms-daemon` | `mail_daemon` | `mail-daemon` |

The root `pyproject.toml` also exposes `mail` and `mail-server` so a workspace
checkout can run them directly (`uv run mail …`, `uv run mail-server`).

### `protocol` — shared types and constants

```text
src/mail_protocol/
├── core/          # Pydantic domain models: messages, drafts, inbox, outbox,
│                  #   trash, swarms, lists, webhooks, user_agents, auth
├── network/       # request/response/webhook wire models
├── constants.py   # protocol version and shared limits
├── core/validators.py
└── cli.py, cli_help.py
```

The protocol package is the dependency root — server, client, and daemon all
import its models. See [Data Models](data-models.md).

### `server` — FastAPI server

```text
src/mail_server/
├── server.py         # app assembly + root/health endpoints + backend selection
├── routers/          # one router per area: auth, swarms, inbox, outbox,
│                     #   drafts, trash, daemon, admin, lists
├── backends/         # storage: base.py (contract), memory/, sqlite/
├── backend_init.py   # the `backend-init` entry point
├── auth.py           # token issuance, refresh tokens, role checks
├── validators.py, utils.py, logging.py, cli.py
└── .env.example      # sample server configuration
```

See [HTTP API](http-api.md), [Storage Backends](storage-backends.md), and
[Configuration](configuration.md).

### `client` — CLI client

```text
src/mail_client/
├── cli.py            # `mail` — user-agent CLI
├── admin_panel.py    # `mail-admin` — admin CLI
└── commands/         # one module per subcommand
```

See [Client CLI](client-cli.md) and [Admin CLI](admin-cli.md).

### `daemon` — delivery daemon

```text
src/mail_daemon/
├── cli.py            # `mail-daemon` entry point
├── maild/            # delivery loop + server API client
└── logger.py
```

See [Daemon CLI](daemon-cli.md) and [Delivery Model](../explanations/delivery-model.md).

## Specification

```text
spec/
├── SPEC.md           # normative protocol prose (versioned, RFC-2119 language)
└── openapi.yaml      # authoritative HTTP wire contract (generated from the app)
```

`openapi.yaml` is generated, not hand-edited — see
[Regenerate API Artifacts](../howtos/regenerate-api-artifacts.md) and
[Protocol Specification](protocol-specification.md).

## Tests

```text
tests/
├── contract/     # spec/openapi conformance (addresses, delivery, messages, drift)
├── e2e/          # end-to-end flows
├── integration/  # auth, authz, and cross-component behavior
└── unit/         # component-level tests
```

See [Run the Test Suite](../howtos/run-tests.md).

## Package documentation

Some packages carry their own `docs/` directory that predates this consolidated
set: `src/mail/server/docs/` and `src/mail/client/docs/`. These are being
migrated into the top-level `docs/` tree; where they overlap, this tree is
canonical.

## Archived v1 runtime

`src/mail/legacy/` holds the MAIL v1 reference runtime (`api.py`, `client.py`,
`core/`, `config/`, UI assets, and its own docs). It is retained for reference
only and is not part of the v2 workspace packages. See
[MAIL v1 Legacy Runtime](../explanations/mail-v1-legacy.md).

[uv]: https://docs.astral.sh/uv/
