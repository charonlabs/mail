# Run the MAIL Server

Status: stub

## Goal

How to start `mail-server` with the desired host, port, backend, and memory
checkpoint behavior.

## Starting Point

The backend has already been initialized and required environment variables are
available.

## Source Material

- `src/mail/server/src/mail_server/cli.py`
- `src/mail/server/src/mail_server/server.py`
- `src/mail/server/.env.example`
- `src/mail/server/docs/reference/cli.md`

## Steps to Cover

1. Set required JWT and host environment variables.
2. Start `uv run mail-server`.
3. Override `--host` and `--port`.
4. Select `--backend memory`.
5. Tune or disable `--memory-save-interval`.
6. Verify `GET /health` or `mail ping`.

## Validation

The server responds with healthy status and the root endpoint reports MAIL
protocol metadata.
