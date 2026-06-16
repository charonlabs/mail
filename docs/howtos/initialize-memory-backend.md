# Initialize the Memory Backend

Status: stub

## Goal

How to create a local memory backend with initial swarms, user-agents, and
credentials for development.

## Starting Point

The repository is cloned, dependencies are installed, and the reader wants local
server state for `mail-server --backend memory`.

## Source Material

- `src/mail/server/src/mail_server/backend_init.py`
- `src/mail/server/src/mail_server/backends/memory/init.py`
- `src/mail/server/docs/tutorials/quickstart.md`

## Steps to Cover

1. Run `uv run backend-init`.
2. Customize deployment, swarm, host, agents, daemons, users, or admins.
3. Locate generated credential files.
4. Remove or protect plaintext password files after capture.
5. Reinitialize clean state when needed.

## Validation

The server starts successfully and the generated user-agents can authenticate.
