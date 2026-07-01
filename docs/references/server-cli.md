# Server CLI

Status: generated

> **Generated file — do not edit by hand.** Regenerate with `uv run python scripts/build_cli_docs.py` after changing the CLI. See [Regenerate API Artifacts](../howtos/regenerate-api-artifacts.md).

The Python/FastAPI server for the Multi-Agent Interface Layer (MAIL)

Invoke as `mail-server` (or `uv run mail-server` from a workspace checkout). Source: `mail_server/cli.py`.

## Options

- `--license` — show license information and exit
- `-H`, `--host` `HOST` — the IP address to bind to (default: 127.0.0.1)
- `-p`, `--port` `PORT` — the port for the server to listen on (default: 8865)
- `-b`, `--backend` `BACKEND` — the MAIL server backend to use (default: memory)
- `--memory-save-interval` `SECONDS` — seconds between memory backend filesystem checkpoints; set 0 to disable (default: 60.0)
- `--sqlite-path` `PATH` — sqlite backend database file (env: MAIL_SQLITE_PATH; default: ~/.mail-swarms/deployments/default/mail.db)
- `--database-url` `URL` — sqlite backend database URL; takes precedence over --sqlite-path (env: MAIL_DATABASE_URL)
