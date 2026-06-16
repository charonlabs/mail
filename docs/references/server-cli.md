# Server CLI

Status: stub

## Scope

Describe the `mail-server` CLI and related backend initialization command.

## Source of Truth

- `src/mail/server/src/mail_server/cli.py`
- `src/mail/server/src/mail_server/backend_init.py`
- `src/mail/server/docs/reference/cli.md`

## Entries to Cover

- `mail-server` usage.
- Host and port options.
- Backend selection.
- Memory checkpoint interval.
- `backend-init` usage.
- Backend initialization options.
- Environment variables required at runtime.

## Maintenance Notes

Keep default values synchronized with parser defaults.
