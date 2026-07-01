# MAIL v1 Legacy Runtime

Status: draft

The MAIL v1 reference runtime is archived under
[`src/mail/legacy/`](../../src/mail/legacy). It is kept for historical reference
and compatibility while the repository moves to the v2 package layout — it is
**not** the current implementation surface. This page explains how to read it
without carrying v1 assumptions into v2 work.

## Why v1 is archived

MAIL v1 bundled the communication contract together with an agent *runtime*:
message/task/action models, tool execution, LiteLLM-backed agent factories, and a
debug UI. MAIL v2 deliberately narrows the protocol to communication only (see
[MAIL v2 Overview](mail-v2-overview.md)), so the v1 runtime no longer reflects how
MAIL is meant to work. Rather than delete it, it is quarantined under
`src/mail/legacy/` so old examples and behavior remain available for reference and
porting.

## What lives there

The archive holds the v1 runtime (`api.py`, `server.py`, `client.py`, `cli.py`,
`core/`), agent factories, standard action libraries, example swarms, the
`swarms.json` machinery, interswarm routing, optional persistence helpers, and the
v1 debug UI — plus archived v1 root artifacts (its `docs/`, configs, Dockerfile,
`README.v1.md`, `AGENTS.v1.md`, `CLAUDE.v1.md`, and tests). Legacy imports use the
`mail.legacy.*` namespace.

## Historical vs active documentation

Treat anything under `src/mail/legacy/` — including its `docs/` — as **historical
reference**. Active guidance is this top-level `docs/` tree plus
[`spec/`](../../spec). Archived prose may still mention old `mail.*` import paths
or v1 endpoints (e.g. the `/ui/*` debug routes) that the v2 server does not
provide; do not treat those as current.

## Running legacy tests

Legacy tests are **not** part of the default suite. Run them explicitly, and only
when maintaining v1 behavior:

```bash
uv run pytest                                   # v2 / default suite
uv run --extra legacy pytest src/mail/legacy/tests   # legacy runtime tests
```

See [Run the Test Suite](../howtos/run-tests.md).

## Working near the archive

- **Don't import v1 architecture into v2 docs or code.** v2 is a communication
  protocol, not a runtime; keep runtime/tool-execution concepts out of v2 pages.
- **Port, don't extend.** Prefer moving behavior forward into the v2 packages over
  growing the v1 APIs. Keep legacy changes scoped to compatibility, security, or
  migration support.
- **Don't modernize examples in place.** Leave v1 examples as-is unless the code
  has actually been ported — a v2-looking example backed by v1 code is misleading.
- **A future UI** should be built against the v2 `mail-server` / `mail-client` /
  `mail-protocol` surfaces, not by adapting the archived v1 UI.

## Related pages

- [Repository Layout](../references/repository-layout.md)
- [MAIL v2 Overview](mail-v2-overview.md)
- [Run the Test Suite](../howtos/run-tests.md)
