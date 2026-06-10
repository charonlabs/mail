# Multi-Agent Interface Layer (MAIL)

MAIL is a protocol and Python implementation for message-oriented coordination
between humans, agents, daemons, and swarms.

This repository is being reorganized for MAIL v2. The active implementation is
split into package-specific workspaces, while the older MAIL v1 reference
runtime is archived under `src/mail/legacy`.

## Active v2 Packages

- `src/mail/protocol` - shared protocol types and constants (`mail-protocol`)
- `src/mail/server` - FastAPI server implementation (`mail-server`)
- `src/mail/client` - command-line client (`mail-client`)
- `src/mail/daemon` - daemon implementation (`mail-daemon`)

## Repository Layout

```text
mail/
├── docs/                 # v2 repository-level docs
├── spec/                 # protocol specification and schemas
├── src/mail/
│   ├── protocol/         # mail-protocol package
│   ├── server/           # mail-server package
│   ├── client/           # mail-client package
│   ├── daemon/           # mail-daemon package
│   └── legacy/           # archived MAIL v1 runtime, docs, config, and UI
├── tests/                # active MAIL v2 test suite
├── scripts/              # repository maintenance scripts
└── pyproject.toml        # uv workspace and meta-package configuration
```

## Development

Install the workspace dependencies:

```bash
uv sync
```

Run the v2 server:

```bash
uv run mail-server
```

Use the v2 client:

```bash
uv run mail --help
```

Run active v2 tests:

```bash
uv run pytest
```

During the transition, some root-level scripts still target the legacy runtime.
Legacy tests and other v1 material live under `src/mail/legacy`.

Run archived legacy tests explicitly:

```bash
uv run pytest src/mail/legacy/tests
```

## Documentation

- Root v2 docs: `docs/README.md`
- Protocol/specification: `spec/`
- Server docs: `src/mail/server/docs/`
- Client docs: `src/mail/client/docs/`
- Legacy runtime notes: `src/mail/legacy/README.md`
- Archived v1 docs: `src/mail/legacy/docs/`

## Legacy Runtime

The MAIL v1 runtime is kept for compatibility and historical reference. Use
`mail.legacy.*` imports for archived code as it is migrated into the legacy
namespace.

Do not add new v2 behavior to the legacy runtime unless it is needed for a
specific compatibility or migration task.

## Licensing

Reference implementation code is licensed under Apache License 2.0. Protocol
specification materials are covered by their repository license files.

