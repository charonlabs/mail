# Configuration

Status: stub

## Scope

List environment variables, CLI defaults, and runtime settings for active MAIL
v2 packages.

## Source of Truth

- `src/mail/server/.env.example`
- `src/mail/server/src/mail_server/cli.py`
- `src/mail/server/src/mail_server/server.py`
- `src/mail/daemon/src/mail_daemon/maild/api.py`
- `src/mail/client/src/mail_client/commands/`

## Entries to Cover

- Server JWT settings.
- `MAIL_HOST`.
- Memory backend checkpoint interval.
- CLI client `MAIL_SERVER`, `MAIL_ADDRESS`, `MAIL_PASSWORD`, and `MAIL_TOKEN`.
- Daemon `MAIL_SERVER`, `MAIL_ADDRESS`, and `MAIL_PASSWORD`.
- Defaults for host, port, backend, and log levels.

## Maintenance Notes

Keep secrets out of examples. Use clearly fake values and link to security
guidance for production deployment decisions.
