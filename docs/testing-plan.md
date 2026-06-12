# MAIL v2 Testing Suite Overhaul Plan

**Status:** Draft — approved for execution
**Date:** 2026-06-12
**Scope:** The v2 packages (`mail-protocol`, `mail-server`, `mail-daemon`,
`mail-client`) and the repository-level `tests/` suite. The legacy suite under
`src/mail/legacy/tests/` is out of scope and remains frozen.

---

## 1. Background

The v2 codebase (~99 source files, ~11.9k LOC across four packages) has
outpaced its test suite by roughly 8:1 in commit volume. The existing suite
(91 tests, all under `tests/unit/`) is well-constructed but covers only the
mailing-lists feature plus CLI parser shape — an estimated 5–8% of the v2
surface. Major subsystems with **zero** coverage today:

- the auth layer (`mail_server.auth`: JWT issue/verify, argon2 hashing,
  role-validation dependencies) — existing endpoint tests monkeypatch it away
- every server router except `lists` (inbox, outbox, drafts, trash, swarms,
  admin, daemon, auth — ~40 endpoints)
- the webhook delivery pipeline (HMAC-SHA256 signing, `X-MAIL-Signature`,
  6-step retry ladder) — six recent fix commits shipped with no tests
- all `mail_client` command behavior (only parser shape is tested)
- the entire `mail_daemon` package
- ~25 of 30 `mail_protocol` validators and most model `summarize()` paths
- ~40 `MemoryBackend` methods beyond the list-store group

One test currently fails
(`test_mail_lists_endpoints.py::test_subscribe_other_rejected_with_403`) due
to drift from commit `570a340` — see Open Decisions (§7).

## 2. Goals

1. Establish four test categories — **unit**, **integration**, **contract**,
   **e2e** — with clear ownership boundaries, so every future v2 change has an
   obvious place for its tests.
2. Cover the subsystems where bugs have actually shipped (webhooks, auth,
   routers) first.
3. Make spec drift mechanically detectable: the implementation, `spec/SPEC.md`,
   and `spec/openapi.yaml` must not be able to diverge silently.
4. Wire coverage measurement so the gap stays visible.

### Non-goals

- Restoring or extending the legacy (`mail.legacy.*`) test suite.
- Performance/load testing (revisit after v2 stabilizes).
- Testing `daemon_deliver_remote` and other interswarm paths beyond stub
  tracking — the feature itself is not implemented yet.

## 3. Target suite architecture

### 3.1 Directory layout

```
tests/
  conftest.py            # shared fixtures (see §3.3)
  unit/                  # pure logic; no network, no real app, tmp_path only
  integration/           # full FastAPI app over ASGI; real auth; real MemoryBackend
    webhooks/            # webhook delivery pipeline (in-process receiver)
  contract/              # spec + OpenAPI conformance
  e2e/                   # real subprocesses, real wire; marked `e2e`
```

### 3.2 Markers and defaults

Registered in `pytest.ini`:

| Marker | Meaning | In default run? |
|---|---|---|
| `unit` | pure logic | yes |
| `integration` | in-process app, real auth | yes |
| `contract` | spec/OpenAPI conformance | yes |
| `e2e` | spawns `mail-server`/`mail-daemon` subprocesses | no (`-m e2e` opt-in; runs in CI) |

`addopts` gains `-m "not e2e"`; CI runs two jobs (default + e2e).
Keep `asyncio_mode = auto`.

### 3.3 Shared fixtures (`tests/conftest.py`)

The ~20-line `deployment_dir` fixture currently duplicated verbatim across
three files moves here, alongside:

- `deployment_dir` — `tmp_path`-backed deployment tree;
  monkeypatches `mail_server.backends.memory.fs.DEPLOYMENT_PATH`
- `backend` — started `MemoryBackend` seeded with a standard cast:
  one admin, two users, one agent, one daemon, one swarm
- `app_client` — `TestClient` over the **real** `mail_server.server.app`
  (env vars `MAIL_HOST`, `MAIL_JWT_SECRET_KEY`, `MAIL_JWT_ALGORITHM` set
  before import), wired to `backend`
- `token_for(address)` — factory issuing real JWTs via `POST /auth/token`,
  so integration tests exercise real auth instead of monkeypatching it
- `webhook_receiver` — in-process ASGI app that records deliveries and can be
  told to fail N times (for retry-ladder tests)

### 3.4 New dev dependencies

- `respx` — `httpx` route mocking for `mail_client` / `mail_daemon` unit tests
- `schemathesis` *(optional, Phase 4)* — property-based fuzzing of endpoints
  against `spec/openapi.yaml`

Coverage: enable `pytest-cov` (already installed) scoped to the four v2
packages; report in CI. Start with a visibility-only report; introduce a
ratchet threshold once Phase 2 lands.

## 4. Test categories — scope definitions

### Unit (`tests/unit/`)

Pure functions and single classes; no app object, no sockets; filesystem only
via `tmp_path`. Owns:

- all `mail_protocol` validators (full matrix: address grammars from SPEC §6,
  uuid/subject/body/name/host bounds from `core/constants.py`)
- Pydantic model construction, validation edges, and `summarize()` for every
  `mail_protocol.core` model (today only `lists` and `trash` are covered)
- `MemoryBackend` method-level behavior (agents/daemons/users/swarms/webhooks
  CRUD, inbox/outbox/drafts/trash operations, buffer semantics)
- `memory.fs` load/save round-trips for every entity type (today: lists only)
- `mail_server.validators` (14 request-body validators → 422 paths)
- `mail_client.commands.*` and `mail_daemon.maild.api` against
  `httpx.MockTransport`/`respx` (daemon tests must reset the module-level
  `_mail_*` globals between tests — add an autouse fixture)
- existing CLI parser-shape tests (stay as-is)

### Integration (`tests/integration/`)

The real composed FastAPI app over ASGI, real JWT auth, real backend, no
subprocesses. Owns:

- **Auth flows:** `POST /auth/token` (good/bad credentials), `whoami` per
  role, password reset, expired/garbage tokens → 401
- **Authorization boundaries:** user cannot read another user's
  inbox/outbox/drafts/trash; non-admin → 403 on all `/admin/*`; daemon-only
  endpoints reject user/admin tokens; agent-role behavior
- **Per-router behavior:** inbox, outbox, drafts (incl. `send`), trash,
  swarms (+ health), admin (19 endpoints), daemon
  (`message-buffer/clear`, `deliver/local`), lists (migrate existing endpoint
  tests here, rewired to real auth)
- **Cross-endpoint flows in-process:** compose → send → buffer → deliver →
  recipient inbox; list fan-out through the real routers
- **Webhook pipeline** (`integration/webhooks/`): delivery POST shape
  (`WebhookDeliveredPostRequest`), HMAC-SHA256 signature verification
  round-trip, retry ladder ordering (patch `asyncio.sleep`; assert the
  0s/1s/30s/5m/1h/6h schedule and give-up behavior), webhook CRUD effects on
  delivery

### Contract (`tests/contract/`)

The spec is the oracle. Owns:

- **OpenAPI drift check:** regenerate the schema exactly as
  `scripts/generate_openapi.py` does and assert equality with the committed
  `spec/openapi.yaml`. A failing check means: change the API deliberately and
  regenerate, or revert.
- **SPEC.md conformance tests:** encode MUST/SHOULD clauses as tests that
  reference their spec section in the test docstring — §6 address grammar
  (host-scoped `user:`/`admin:`/`daemon:` forms, swarm-scoped agent and
  `list:` forms), §7 message field requirements and bounds, §8 pre-send vs
  post-send error semantics. Where the implementation and spec disagree, the
  test fails and forces the conversation.
- **Schemathesis fuzzing** *(optional)*: generate requests from the OpenAPI
  schema against the in-process app; assert no 500s and response-schema
  conformance.

### E2E (`tests/e2e/`)

Real processes, real wire, few in number. A session-scoped fixture runs
`backend-init` into a tmp deployment, then launches `mail-server` (uvicorn)
and `mail-daemon` subprocesses with real env wiring, polling `/health` for
readiness. Tests drive the system through the `mail` / `mail-admin` CLIs:

1. **Send/deliver journey:** login → compose → send → daemon delivers →
   recipient sees the message via `inbox` / `inbox-open`
2. **List fan-out journey:** admin creates list → users subscribe → send to
   `list:` address → all members receive
3. **Persistence across restart:** send/deliver → stop server cleanly →
   relaunch on same deployment dir → inbox/outbox/lists intact
4. **Auth journey:** login, whoami, bad-password rejection, admin panel access

These are the only tests that can catch env-var wiring, `backend_init`
provisioning, daemon global state, and shutdown persistence in combination.

## 5. Execution phases

Each phase is independently mergeable and leaves the default suite green.

### Phase 0 — Foundation (small)
- Resolve the failing `test_subscribe_other_rejected_with_403` per the §7
  decision.
- Create `tests/conftest.py`; deduplicate the `deployment_dir` fixture out of
  the three files that copy it.
- Create the category directories, register markers, update `pytest.ini`
  (`-m "not e2e"`), move `tests/unit/` content as needed (no test rewrites).
- Wire `pytest-cov` reporting; gitignore `pytest.log`.
- Add `respx` as a dev dependency.

**Exit:** suite green; one shared fixture set; coverage number visible.

### Phase 1 — Integration: auth + routers (largest single phase)
- `app_client` + `token_for` fixtures (real app, real JWTs).
- Auth flow and authorization-boundary tests.
- Per-router endpoint tests for inbox, outbox, drafts, trash, swarms, admin,
  daemon; migrate lists endpoint tests onto real auth.
- `xfail(raises=NotImplementedError)` tests for the known stubs
  (`delete_inbox_message`, `delete_draft`, `delete_trash_message`,
  `clear_trash`, `daemon_deliver_remote`, `admin_webhook_patch`) so the
  checklist is executable.

**Exit:** every registered route has ≥1 success and ≥1 authz/failure test;
auth layer no longer monkeypatched anywhere in integration tests.

### Phase 2 — Webhook delivery pipeline
- `webhook_receiver` fixture; signature round-trip, payload shape, retry
  ladder with patched sleep, give-up after final attempt, CRUD→delivery
  effects.

**Exit:** the six-commit bug cluster's behaviors are all pinned by tests.

### Phase 3 — Contract layer
- OpenAPI drift check.
- SPEC.md §6/§7/§8 conformance tests with section-referencing docstrings.
- Decide on schemathesis adoption after evaluating runtime cost.

**Exit:** an API change that isn't reflected in `spec/openapi.yaml` fails CI.

### Phase 4 — Client + daemon units, protocol back-fill
- `mail_client.commands.*` against mocked transport (request shape, token
  header, output rendering incl. markdown path); `mail-admin` commands.
- `mail_daemon.maild.api`: loop iteration behavior, buffer-clear/deliver
  calls, startup validation, token acquisition; globals-reset fixture.
- Back-fill `mail_protocol` validator matrix, model edges, `memory.fs`
  round-trips for all entity types, `mail_server.validators`.

**Exit:** every v2 package has meaningful unit coverage; set the initial
coverage ratchet.

### Phase 5 — E2E journeys + CI
- Subprocess harness fixture; the four journeys in §4.
- CI: default job (unit+integration+contract, coverage report) and e2e job.

**Exit:** full-system happy paths run on every PR.

## 6. Conventions

- New v2 features land with tests in the matching category; bug fixes land
  with a regression test (the webhook cluster is the cautionary tale).
- Conformance tests cite their SPEC.md section; when implementation and spec
  conflict, the spec is amended or the code fixed — never the test deleted
  silently.
- Stubbed functionality gets an `xfail(raises=NotImplementedError)` test at
  introduction time.
- Shared fixtures live in `tests/conftest.py`; category-specific ones in that
  category's `conftest.py`. No copy-pasted fixtures.

## 7. Open decisions

1. **Subscribe-on-behalf semantics — RESOLVED 2026-06-12: option (a).**
   Commit `570a340` removed the request body from
   `POST /lists/{list}/subscribe`; the endpoint always subscribes the
   authenticated caller. This is ratified: subscribing *another* user-agent
   is an admin-only capability (via `/admin/lists/{list}/members`), so the
   public endpoint stays body-less. The stale 403 test is replaced by
   `test_subscribe_ignores_supplied_member_address`. `spec/openapi.yaml`
   already reflects the body-less endpoint; no spec change needed.
2. **Coverage ratchet level.** Proposed: visibility-only until Phase 2, then
   set the floor at the then-current number and raise it per phase.
3. **Schemathesis adoption** (Phase 3): adopt if a fuzz run stays under ~60s
   locally; otherwise defer to a nightly CI job.
