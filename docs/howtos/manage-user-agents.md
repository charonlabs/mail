# Manage User-Agents

Status: draft

## Goal

Create, inspect, and remove MAIL agents, users, and daemons with the `mail-admin`
CLI.

## Starting Point

You have an **admin** `MAIL_TOKEN` for the target server (see
[Authenticate a User-Agent](authenticate-user-agent.md)). Admin accounts
themselves are created by `backend-init`, not by these commands — see
[Initialize the Memory Backend](initialize-memory-backend.md). For the address
shapes used below, see [Addressing Model](../explanations/addressing-model.md).

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={admin_jwt}
```

## Steps

### 1. List existing user-agents by type

```bash
uv run mail-admin agent-list
uv run mail-admin user-list
uv run mail-admin daemon-list
```

### 2. Create an agent in a swarm

Agents are swarm-scoped, so the argument is the **local** `agent@swarm` form. The
command prompts for the new agent's password interactively (hidden input) rather
than taking it as an argument, keeping secrets out of shell history:

```bash
uv run mail-admin agent-post supervisor@default
# agent password: ********
```

### 3. Create a host-scoped user or daemon

Users and daemons are host-scoped, so they take a bare id / worker name; both
prompt for a password:

```bash
uv run mail-admin user-post alice          # -> user:alice@{host}
uv run mail-admin daemon-post worker-1      # -> daemon:worker-1@{host}
```

### 4. Inspect a user-agent

```bash
uv run mail-admin agent-get supervisor@default
uv run mail-admin user-get alice
uv run mail-admin daemon-get worker-1
```

### 5. Delete a user-agent

```bash
uv run mail-admin agent-delete supervisor@default
uv run mail-admin user-delete alice
uv run mail-admin daemon-delete worker-1
```

## Verification

A created user-agent appears in the matching `*-list` / `*-get` output and can
authenticate with its generated password. Handle admin credentials with care —
they are effectively server-control credentials (see
[Security Model](../explanations/security-model.md)).

## See also

- [Admin CLI](../references/admin-cli.md) — full `mail-admin` reference.
- [Manage Swarms](manage-swarms.md) — swarms an agent lives in.
- [Security Model](../explanations/security-model.md)

## Source Material

- `src/mail/client/src/mail_client/admin_panel.py`
- `src/mail/client/src/mail_client/commands/agent_post.py`
- `src/mail/client/src/mail_client/commands/user_post.py`
- `src/mail/client/src/mail_client/commands/daemon_post.py`
