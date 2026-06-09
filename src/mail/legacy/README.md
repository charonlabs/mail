# MAIL Legacy Runtime

This directory contains the MAIL v1 reference runtime and its related examples,
tools, and support code. It is retained for historical compatibility while the
repository moves toward the MAIL v2 package layout.

The active v2 packages live beside this directory:

- `src/mail/protocol` - protocol types and constants, distributed as `mail-protocol`
- `src/mail/server` - v2 HTTP server, distributed as `mail-server`
- `src/mail/client` - v2 CLI/client package, distributed as `mail-client`
- `src/mail/daemon` - daemon package, distributed as `mail-daemon`

Legacy code should not be treated as the current implementation surface for new
v2 work. Prefer the v2 packages above unless you are maintaining v1 behavior,
porting functionality forward, or preserving old examples for reference.

## What Lives Here

The legacy runtime currently includes:

- `api.py` - v1 high-level swarm, agent, and action APIs
- `cli.py` - v1 CLI implementation
- `server.py` - v1 FastAPI server, including debug UI endpoints
- `client.py` - v1 async HTTP client and client CLI helpers
- `core/` - v1 runtime, messages, tasks, actions, tools, and agents
- `factories/` - v1 LiteLLM-backed agent factories
- `stdlib/` - v1 reusable action libraries
- `examples/` - v1 example swarms, prompts, and demo agents
- `swarms_json/` - v1 swarm definition parsing and validation
- `net/` - v1 interswarm routing and registry support
- `db/` - v1 optional persistence helpers
- `utils/` - v1 parsing, logging, auth, serialization, and support utilities

The following v1-oriented root artifacts have been archived under this
directory:

- `docs/`
- `configs/mail.toml`
- `configs/swarms.json`
- `Dockerfile`
- `ui/`
- `README.v1.md`
- `assets/`
- `AGENTS.v1.md`
- `CLAUDE.v1.md`
- `tests/`

The repository still has root-level files that are v1-oriented and should move
here in later cleanup passes:

- `scripts/` that run v1 swarms or v1 smoke tests

## Import Namespace

The intended archive namespace is `mail.legacy`.

Use this form for legacy imports after the cleanup:

```python
from mail.legacy import MAILSwarmTemplate
from mail.legacy.core.runtime import MAILRuntime
from mail.legacy.factories.supervisor import LiteLLMSupervisorFunction
```

Legacy `swarms.json` import strings should also use `mail.legacy`:

```json
"factory": "python::mail.legacy.factories.supervisor:LiteLLMSupervisorFunction"
```

The legacy runtime and tests now use `mail.legacy.*` imports. Archived prose
docs may still mention historical `mail.*` paths until those pages are touched
for content updates.

## Documentation Policy

Root documentation should describe MAIL v2 and the repository as it exists now.
Detailed v1 runtime documentation belongs here under `src/mail/legacy/docs/`.

When moving old docs into this archive:

- Keep the original historical content where useful.
- Keep a visible archive note in `docs/README.md`; add page-level notes as
  individual pages are touched.
- Update links from `src/mail/...` to `src/mail/legacy/...` when they refer to
  v1 code.
- Do not update v1 examples to look like v2 APIs unless the code has actually
  been ported.

## Tests And Scripts

Legacy tests live under `src/mail/legacy/tests/` and run with an explicit
command, separate from the default v2 test suite.

Recommended commands:

```bash
# v2/default tests
uv run pytest

# legacy runtime tests
uv run pytest src/mail/legacy/tests
```

Legacy smoke scripts and demos should live under `src/mail/legacy/scripts/`.
Root `scripts/` should be reserved for repository maintenance tasks that apply
to the v2 workspace as a whole.

## UI Status

The existing `ui/` application targets v1 debug endpoints such as `/ui/message`,
`/ui/tasks`, `/ui/task/{task_id}`, and `/ui/agents`. Those endpoints are defined
by the legacy server, not the current v2 server package.

For now, archive the UI with the legacy runtime. A future v2 UI should be built
against the v2 `mail-server`, `mail-client`, and `mail-protocol` surfaces rather
than adapting the archived UI in place.

## Maintenance Rules

- Keep changes to legacy code scoped to compatibility, security, or migration
  support.
- Prefer porting behavior into v2 packages instead of extending v1 APIs.
- If a root file primarily documents or exercises `mail.legacy`, move it here.
- If a root file describes protocol-level behavior that is still current, keep
  it at the root or under `spec/`.
- Keep the legacy archive buildable where practical, but do not let legacy
  compatibility block v2 package cleanup.

