# MAIL Server Backends

`mail-server` stores all of its state — user-agents, swarms, messages, the four
boxes (inbox/outbox/drafts/trash), the delivery buffer, webhooks, and lists —
through a pluggable backend. Two backends ship today, selected with
`--backend` (see [cli.md](cli.md)):

| | `memory` (default) | `sqlite` |
|---|---|---|
| Store | process-local dicts | SQLite file (SQLAlchemy async + `aiosqlite`) |
| Durability | periodic checkpoint + shutdown flush | per-commit (transactional) |
| Survives `kill -9` | only up to the last checkpoint | yes — committed writes are durable |
| Pagination / sorting | in Python over the whole box | pushed into SQL (`ORDER BY ... LIMIT`) |
| Method coverage | core; some endpoints are stubs | full parity (implements the stubs too) |
| Scaling | single process | single node |

Both implement the same `MAILServerBackend` protocol, so the HTTP API is
identical regardless of which one is selected.

## `memory` backend

The default. Holds all state in process-local dictionaries and persists it to a
directory tree under `~/.mail-swarms/deployments/<deployment>/` on shutdown and
on a periodic checkpoint (`--memory-save-interval`, default 60s). It is the
reference proof-of-concept: simple and dependency-light, but durability is
bounded by the checkpoint interval — an abrupt `kill -9` loses everything
written since the last checkpoint.

A handful of endpoints (`DELETE /inbox/{id}`, `DELETE /drafts/{id}`,
`DELETE /trash/{id}`, `POST /trash/clear`, `POST /daemon/deliver/remote`,
`PATCH /admin/webhooks/{id}`) raise `NotImplementedError` on this backend.

## `sqlite` backend

A durable, transactional backend over a single SQLite file. Every write commits
in its own short transaction, so a committed message survives an abrupt
`kill -9` — the window the memory backend's checkpoint cannot close.
Pagination, sorting, and filtering are pushed into SQL rather than loaded into
Python. It implements **every** protocol method, including the ones the memory
backend leaves as stubs, making it the more complete backend.

### Database location

Resolution precedence (highest first):

1. `--database-url` / `MAIL_DATABASE_URL` — a full URL, e.g.
   `sqlite:////absolute/path/mail.db`.
2. `--sqlite-path` / `MAIL_SQLITE_PATH` — a file path.
3. Default: `~/.mail-swarms/deployments/default/mail.db`.

A `sqlite://` URL is normalized to the async `sqlite+aiosqlite://` driver
automatically, and the parent directory is created if missing.

### Connection settings

Each connection is opened with:

- `journal_mode=WAL` — readers never block the writer.
- `foreign_keys=ON` — referential integrity is enforced (cascade deletes work).
- `busy_timeout=5000` — brief write contention retries for up to 5s instead of
  immediately raising `database is locked`.

### Initialization

Provision a SQLite deployment with `backend-init --type sqlite` (same argument
surface as the memory initializer — deployment, swarm, agents, daemons, users,
admins, host):

```bash
backend-init --type sqlite --swarm chorus --host localhost \
  --agents supervisor --users alice --admins root --daemons dummy
```

This creates the database file and schema and seeds the swarm and user-agents,
writing each generated password to `~/.mail-swarms/deployments/<deployment>/.secrets/<address>`.
Re-running is safe: existing swarms and user-agents are left untouched. No box
files are created — per-owner box membership is created lazily on first
delivery.

Then run the server against the same database:

```bash
mail-server --backend sqlite
```

(The startup lifespan creates the schema if it does not already exist, so
running `mail-server --backend sqlite` against a fresh path also works; use
`backend-init` when you want a seeded cast.)

### Migrating an existing `memory` deployment

If you already have a filesystem (`memory`) deployment, you can import it into a
new SQLite database of the same name instead of seeding a fresh cast:

```bash
backend-init --type sqlite --import-fs
```

This reads the existing `~/.mail-swarms/deployments/<deployment>/` tree (user-agents,
swarms, messages, all four boxes with their ordering, the delivery buffer,
webhooks, and lists) and writes it into `<deployment>/mail.db`. Existing
`.secrets/` files are untouched, so credentials carry over. The import runs in a
single transaction and **refuses to run against a non-empty database**, so it
can't clobber an existing SQLite deployment.

### Single-node caveat

SQLite serializes writers even in WAL mode, and `aiosqlite` runs each connection
on a thread, so concurrent requests can still contend on the write lock (the
`busy_timeout` retry absorbs brief contention). This makes the `sqlite` backend
a good fit for **single-node durable deployments**. Horizontal, multi-process
scaling wants a client/server database such as PostgreSQL; the URL-normalization
seam leaves the door open for a future Postgres backend, but that is not part of
this release.
