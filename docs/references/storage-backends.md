# Storage Backends

Status: draft

The MAIL server keeps all state behind a single backend interface. Two backends
ship today — an in-memory backend with filesystem checkpointing, and a
transactional SQLite backend. Both implement the same contract, so the choice is
about durability and operational shape, not features. Code is under
[`src/mail/server/src/mail_server/backends/`](../../src/mail/server/src/mail_server/backends).

## The backend contract

`MAILServerBackend`
([`backends/base.py`](../../src/mail/server/src/mail_server/backends/base.py)) is
a `typing.Protocol` of `@abstractmethod`s that both backends implement. It has one
concrete attribute, `host: str` (set at startup; routers use it to reconstruct
full addresses), and the abstract methods group into:

| Area | Responsibility |
| --- | --- |
| Lifecycle | `on_server_startup`, `on_server_shutdown` |
| Auth / user-agents | fetch a user-agent, existence check, password reset |
| Refresh tokens | create, get, rotate, revoke-family, revoke-all, purge-expired |
| Swarms | list, get, health |
| Boxes | inbox / outbox / drafts / trash: list, get, delete (+ draft create/patch/send, trash clear) |
| Daemon delivery | clear message buffer, deliver local, deliver remote |
| Admin | CRUD for agents, daemons, users, swarms |
| Webhooks | CRUD, plus the shared outbound delivery logic |
| Lists | list/get (public + admin), create, patch, delete, add/remove member |

The only **concrete** methods on the base are the webhook-delivery helpers
(`handle_webhook_delivered_for_url`, `_webhook_delivered_post`), so both backends
share identical `mail.delivered` HMAC signing and retry behavior — see
[Webhook Delivery](../explanations/webhook-delivery.md).

## Selecting a backend

`mail-server --backend {memory,sqlite}` (`-b`, default `memory`). There is no env
var for the backend choice itself; per-backend knobs are covered in
[Configuration](configuration.md). `backend-init --type {memory,sqlite}`
initializes on-disk state before the server starts — see
[Initialize the Memory Backend](../howtos/initialize-memory-backend.md).

## Memory backend

Files: `backends/memory/api.py` (state + logic), `fs.py` (load/save), `init.py`
(`backend-init` seeding).

- **Model.** All state lives in Python dicts/lists in RAM. On startup every
  collection is loaded from disk; on checkpoint and shutdown every collection is
  written back.
- **On-disk layout** under `~/.mail-swarms/deployments/{deployment}/`: one
  directory per collection with one JSON file per item
  (`swarms/`, `user_agents/`, `messages/`, `inbox_entries/`, `outbox_entries/`,
  `draft_entries/`, `trash_entries/`, `webhooks/`, `lists/`, `refresh_tokens/`),
  newline-delimited membership files for each per-owner box
  (`inboxes/`, `outboxes/`, `drafts/`, `trashes/`, `read_inbox/`), a
  `message_buffer.lock` FIFO file, and the plaintext `.secrets/<address>` files
  written at init.
- **Checkpointing.** A background loop persists every
  `--memory-save-interval` seconds (default **60**, `0` disables the periodic
  loop), plus a final persist on shutdown. Each file write is atomic (temp file
  → `fsync` → `os.replace` → parent-dir `fsync`).
- **Durability caveats.** State between checkpoints is RAM-only: a hard kill (or
  interval `0`) loses everything since the last checkpoint. Individual writes are
  atomic, but a full checkpoint is not a single transaction across collections, so
  a crash mid-persist can leave collections at slightly different versions.

## SQLite backend

Files: `backends/sqlite/` — `api.py`, `database.py`, `schema.py`,
`repositories.py`, `serializers.py`, `init.py`, `migrate.py`.

- **Model.** Fully transactional and durable. Every mutation runs in a session
  that commits on success / rolls back on error; multi-step operations (e.g.
  `send_draft` = message + outbox entry + membership + buffer row) commit
  atomically. There is no in-RAM master copy and no checkpoint loop — every write
  hits the database.
- **Stack.** Async SQLAlchemy over `sqlite+aiosqlite`, with per-connection
  `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, and `busy_timeout=5000` (5s).
- **Schema (hybrid).** Entity rows carry typed/indexed columns only for
  filtering/ordering, plus a `body` JSON column holding the full
  `model.model_dump(mode="json")`; reads rehydrate from `body`. Tables:
  `user_agents`, `swarms`, `messages`, `inbox_entries`, `outbox_entries`,
  `draft_entries`, `trash_entries`, `mailbox_items` (unified per-owner box
  membership + ordering, with `is_read` for the inbox), `message_buffer`,
  `webhooks`, `refresh_tokens` (all-typed, no body), `lists`.
- **Location.** Default `~/.mail-swarms/deployments/{deployment}/mail.db`;
  overridable via `--sqlite-path` / `MAIL_SQLITE_PATH` or a full
  `--database-url` / `MAIL_DATABASE_URL` (precedence: database-url > sqlite-path >
  default).
- **Migrations.** No migration framework. `create_schema()` runs
  `create_all` plus an additive, idempotent `ALTER TABLE ... ADD COLUMN` guard for
  new queryable columns (the current guard adds `mailbox_items.is_read`,
  backfilling existing rows as unread).

## Initializing state with `backend-init`

- `--type memory` builds the full deployment directory tree, writes the swarm and
  each user-agent (hashed password), touches empty box files, and writes plaintext
  `.secrets/<address>`.
- `--type sqlite` creates `mail.db` + schema and seeds one swarm + the requested
  principals; it is idempotent on re-run (existing swarm/user-agents skipped) and
  creates box membership lazily on first delivery. Plaintext secrets are still
  written.
- `--type sqlite --import-fs` imports an existing memory/filesystem deployment of
  the same name into a fresh SQLite database (messages first, then box entries,
  then membership in arrival order, then buffer/webhooks/lists — all in one
  transaction). It refuses to run if the source is missing or the target DB
  already holds rows.

## Capability differences

| Aspect | Memory | SQLite |
| --- | --- | --- |
| Durability | RAM-first; ≤1 checkpoint interval at risk on crash | Durable per write (WAL) |
| Transactions | Per-file atomic writes; not cross-collection | Full multi-step transactions |
| Concurrency | Single `asyncio.Lock` around persist | WAL readers + serialized writers, 5s busy timeout |
| Deployments | Runtime reads/writes the `default` deployment only (see limitations) | Arbitrary via `--sqlite-path` / `--database-url` |
| Init on re-run | Overwrites | Idempotent |
| Migration import | — | `--import-fs` |
| Delete/clear, webhook patch, remote deliver | Not implemented (raises `NotImplementedError`) | Implemented |

Both implement the identical interface and share the webhook delivery logic, so
inbox `is_read`, refresh-token families, list membership, and webhook semantics
match across backends.

## Current limitations

- **Memory backend: unimplemented operations.** Several operations raise
  `NotImplementedError` on the memory backend and are only available on SQLite:
  `DELETE /inbox/{message_id}`, `DELETE /drafts/{draft_id}`,
  `DELETE /trash/{message_id}`, `POST /trash/clear`,
  `PATCH /admin/webhooks/{webhook_id}`, and `POST /daemon/deliver/remote`. Choose
  the SQLite backend if you need message deletion / trash clearing, webhook
  patching, or inbound remote delivery. These gaps are pinned as `xfail` in
  [`tests/integration/test_stubs.py`](../../tests/integration/test_stubs.py).
- **Memory backend deployment name.** The memory runtime's filesystem layer is
  pinned to the `default` deployment: `backend-init` will *create* a named memory
  deployment, but `mail-server --backend memory` reads and writes `default`
  regardless. Use the SQLite backend for non-default deployment names.
- No Postgres backend yet, though `normalize_database_url` reserves a
  `postgresql+psycopg` driver seam.

## Maintenance notes

Keep production deployment advice in how-to or explanation pages unless it is a
direct backend capability or limitation. Update this page when the backend
contract, on-disk layout, or SQLite schema changes.
