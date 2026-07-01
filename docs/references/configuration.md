# Configuration

Status: draft

This page lists every environment variable and CLI flag across the four MAIL v2
packages, with defaults and whether each is required. Default host/port come from
[`mail_protocol.constants`](../../src/mail/protocol/src/mail_protocol/constants.py):
`MAIL_DEFAULT_HOST = 127.0.0.1`, `MAIL_DEFAULT_PORT = 8865`.

## Server (`mail-server`)

### Required environment variables

These are read at import/startup — the server process fails to boot (raising
`RuntimeError`) if any is unset.

| Variable | Effect |
| --- | --- |
| `MAIL_HOST` | Canonical host identity for the deployment/swarm. |
| `MAIL_JWT_SECRET_KEY` | HMAC secret for signing/verifying access-token JWTs. |
| `MAIL_JWT_ALGORITHM` | JWT signing algorithm (e.g. `HS256`). |
| `MAIL_JWT_EXPIRE_MINUTES` | Access-token lifetime, in minutes. |
| `MAIL_REFRESH_TOKEN_EXPIRE_DAYS` | Absolute lifetime of a refresh-token family, in days. |

### Optional environment variables

| Variable | Default | Effect |
| --- | --- | --- |
| `MAIL_COOKIE_SECURE` | `"true"` | Refresh-cookie `Secure` flag; only the literal `false` disables it. |
| `MAIL_COOKIE_DOMAIN` | unset (host-only cookie) | Cookie `Domain` for cross-subdomain deployments. |
| `MAIL_MEMORY_SAVE_INTERVAL_SECONDS` | `60.0` | Default for `--memory-save-interval`; `0` disables periodic checkpoints. |
| `MAIL_SQLITE_PATH` | unset → default DB path | Default for `--sqlite-path`. |
| `MAIL_DATABASE_URL` | unset | Default for `--database-url`; takes precedence over the sqlite path. |

### CLI flags

| Flag | Default | Effect |
| --- | --- | --- |
| `-H`, `--host` | `127.0.0.1` | Bind address. |
| `-p`, `--port` | `8865` | Listen port. |
| `-b`, `--backend` | `memory` | `memory` or `sqlite` (see [Storage Backends](storage-backends.md)). |
| `--memory-save-interval` | `$MAIL_MEMORY_SAVE_INTERVAL_SECONDS` or `60.0` | Seconds between memory checkpoints; `0` disables. |
| `--sqlite-path` | `$MAIL_SQLITE_PATH` or default DB path | SQLite database file. |
| `--database-url` | `$MAIL_DATABASE_URL` | Full database URL. |
| `--license` | — | Print license and exit. |

**Database URL resolution** (SQLite backend): `--database-url` > `--sqlite-path`
> default `~/.mail-swarms/deployments/default/mail.db`.

**Logging** is not configurable on the server: level is fixed at `INFO` and logs
are written to `~/.mail-swarms/server_logs/<YYYY_MM_DD>.log`.

## Client (`mail` and `mail-admin`)

Client commands read these per-invocation and raise `ValueError` if a required
one is missing. Tokens are never written by the client — `login` and `refresh`
print them for you to export.

| Variable | Required for | Effect |
| --- | --- | --- |
| `MAIL_SERVER` | all commands | Base URL of the target server. |
| `MAIL_TOKEN` | all authenticated commands | Bearer access token. Not used by `ping` or `login`. |
| `MAIL_ADDRESS` | `login` | Address for the password grant. |
| `MAIL_PASSWORD` | `login` | Password for the password grant. |
| `MAIL_REFRESH_TOKEN` | `refresh` | Refresh token sent to `POST /auth/refresh` (rotated server-side). |

CLI flag: `-o`/`--output` selects output format — `text` (default), `json`
(`mail` also supports `markdown`). Both accept `--license`. See
[Authenticate a User-Agent](../howtos/authenticate-user-agent.md).

## Daemon (`mail-daemon`)

Required environment variables (raise `ValueError` at startup if unset):

| Variable | Effect |
| --- | --- |
| `MAIL_SERVER` | Target server URL (also health-checked at startup). |
| `MAIL_ADDRESS` | Daemon login address. |
| `MAIL_PASSWORD` | Daemon login password. |

CLI flags: `-llf`/`--log-level-file` and `-llc`/`--log-level-console` (both
default `info`; choices `debug|info|warning|error|critical`), plus `--license`.
The 30-second delivery poll interval is a hard-coded default with no flag or env
var. See [Run the MAIL Daemon](../howtos/run-daemon.md).

## `backend-init`

`backend-init` takes no environment variables; all configuration is via flags
(`--type`, `--deployment`, `--swarm`, `--swarm-description`, `--swarm-keywords`,
`--agents`, `--daemons`, `--users`, `--admins`, `--host`, `--import-fs`). Defaults
and usage are in
[Initialize the Memory Backend](../howtos/initialize-memory-backend.md).

## `.env.example`

[`src/mail/server/.env.example`](../../src/mail/server/.env.example) is a
server-side template containing `MAIL_HOST`, `MAIL_JWT_SECRET_KEY` (fake value),
`MAIL_JWT_ALGORITHM`, `MAIL_JWT_EXPIRE_MINUTES`, `MAIL_REFRESH_TOKEN_EXPIRE_DAYS`,
`MAIL_COOKIE_SECURE`, and a commented-out `MAIL_COOKIE_DOMAIN`. The optional
backend knobs (`MAIL_MEMORY_SAVE_INTERVAL_SECONDS`, `MAIL_SQLITE_PATH`,
`MAIL_DATABASE_URL`) and client/daemon variables are not in it.

## Maintenance notes

Keep secrets out of examples — use clearly fake values, and link to
[Security Model](../explanations/security-model.md) for production guidance
(TLS, reverse proxy, secret handling). Update this page when a variable or flag is
added, renamed, or changes its default or required status.
