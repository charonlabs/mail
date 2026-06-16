# Admin CLI

Status: stub

## Scope

Describe the administrator command-line surface for managing MAIL server
resources.

## Source of Truth

- `src/mail/client/src/mail_client/admin_panel.py`
- `src/mail/client/src/mail_client/commands/agent_*.py`
- `src/mail/client/src/mail_client/commands/user_*.py`
- `src/mail/client/src/mail_client/commands/daemon_*.py`
- `src/mail/client/src/mail_client/commands/swarm_*.py`
- `src/mail/client/src/mail_client/commands/webhook_*.py`
- `src/mail/client/src/mail_client/commands/list_*.py`
- `src/mail/client/docs/reference/admin-panel.md`

## Entries to Cover

- Agent operations.
- User operations.
- Admin operations if exposed.
- Daemon operations.
- Swarm operations.
- Webhook operations.
- Mailing list administration.
- Shared auth and output options.

## Maintenance Notes

Call out destructive commands clearly, but keep procedural guidance in how-to
pages.
