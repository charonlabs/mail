# Manage Swarms

Status: stub

## Goal

How to create, inspect, and delete MAIL swarms.

## Starting Point

The reader has an admin token for changes or a regular user-agent token for
read-only swarm inspection.

## Source Material

- `src/mail/client/src/mail_client/commands/swarm_list.py`
- `src/mail/client/src/mail_client/commands/swarm_get.py`
- `src/mail/client/src/mail_client/commands/swarm_post.py`
- `src/mail/client/src/mail_client/commands/swarm_delete.py`
- `src/mail/server/src/mail_server/routers/swarms.py`
- `src/mail/server/src/mail_server/routers/admin.py`

## Steps to Cover

1. List swarms.
2. Inspect a swarm by name.
3. Create a swarm as an admin.
4. Add initial description, keywords, and agents.
5. Delete a test swarm.

## Validation

The created swarm is visible through public swarm lookup and removable through
admin commands.
