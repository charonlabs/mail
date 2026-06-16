# Manage User-Agents

Status: stub

## Goal

How to create, inspect, and remove MAIL agents, users, admins, and daemons with
administrator tooling.

## Starting Point

The reader has an admin token for the target server.

## Source Material

- `src/mail/client/docs/reference/admin-panel.md`
- `src/mail/client/src/mail_client/admin_panel.py`
- `src/mail/client/src/mail_client/commands/agent_post.py`
- `src/mail/client/src/mail_client/commands/user_post.py`
- `src/mail/client/src/mail_client/commands/daemon_post.py`
- `src/mail/server/src/mail_server/routers/admin.py`

## Steps to Cover

1. Authenticate as an admin.
2. List existing user-agents by type.
3. Create an agent in a swarm.
4. Create a host-scoped user or daemon.
5. Inspect the created user-agent.
6. Delete a test user-agent.

## Validation

Created user-agents appear in admin list/get commands and can authenticate when
credentials are valid.
