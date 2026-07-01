# Run the MAIL Server

Status: draft

## Goal

Start `mail-server` with the host, port, backend, and checkpoint behavior you
want.

## Starting Point

Workspace dependencies are installed (`uv sync`) and you have initialized a
backend — see [Initialize the Memory Backend](initialize-memory-backend.md).

## Steps

### 1. Set the required environment variables

The server reads these at startup and refuses to boot if any is missing. Copy
[`src/mail/server/.env.example`](../../src/mail/server/.env.example) as a
starting point; full details are in [Configuration](../references/configuration.md).

```bash
MAIL_HOST=localhost
MAIL_JWT_SECRET_KEY=$(openssl rand -hex 32)
MAIL_JWT_ALGORITHM=HS256
MAIL_JWT_EXPIRE_MINUTES=30
MAIL_REFRESH_TOKEN_EXPIRE_DAYS=30
```

### 2. Start the server

```bash
uv run mail-server
```

With no flags the server uses the memory backend and listens on
`http://127.0.0.1:8865`.

### 3. Override host and port

```bash
uv run mail-server --host 0.0.0.0 --port 9000
```

### 4. Choose a backend

The default is `memory`; use `sqlite` for a durable, transactional store:

```bash
uv run mail-server --backend sqlite --sqlite-path ./mail.db
```

See [Storage Backends](../references/storage-backends.md) for the trade-offs and
for `--database-url`. (Note: the memory backend always reads/writes the `default`
deployment; use SQLite for other deployment names.)

### 5. Tune or disable memory checkpointing

The memory backend checkpoints to disk every `--memory-save-interval` seconds
(default 60). Set `0` to disable periodic checkpoints (a final save still runs on
shutdown):

```bash
uv run mail-server --backend memory --memory-save-interval 10
```

### 6. Verify it is up

```bash
curl -s http://127.0.0.1:8865/health      # -> {"status":"ok"}
# or, with the client configured:
MAIL_SERVER=http://127.0.0.1:8865 uv run mail ping
```

`GET /` reports the protocol name, version, and uptime.

## See also

- [Configuration](../references/configuration.md) — every server flag and env var.
- [Run the MAIL Daemon](run-daemon.md) — needed for messages to actually deliver.
- [Storage Backends](../references/storage-backends.md)

## Source Material

- `src/mail/server/src/mail_server/cli.py`
- `src/mail/server/src/mail_server/server.py`
- `src/mail/server/.env.example`
