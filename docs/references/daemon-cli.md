# Daemon CLI

Status: stub

## Scope

Describe the `mail-daemon` CLI, required environment variables, and daemon loop
behavior.

## Source of Truth

- `src/mail/daemon/src/mail_daemon/cli.py`
- `src/mail/daemon/src/mail_daemon/maild/api.py`
- `spec/SPEC.md` section 8

## Entries to Cover

- Usage.
- Log-level options.
- Required environment variables.
- Server validation.
- Token acquisition.
- Message buffer clearing.
- Local delivery.
- Retry and error behavior.

## Maintenance Notes

Keep behavioral details factual and tied to implementation. Deeper discussion of
why delivery is daemon-driven belongs in explanations.
