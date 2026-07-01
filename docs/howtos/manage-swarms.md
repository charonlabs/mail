# Manage Swarms

Status: draft

## Goal

How to create, inspect, and delete MAIL swarms.

## Starting Point

The reader has an admin token for changes or a regular user-agent token for
read-only swarm inspection.

## Steps

### 1. List swarms

Authorized user-agents can list all swarms on a MAIL server via the `mail` CLI command `swarms-list`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={ua_jwt}
uv run mail swarms-list
```

This will print the name, keywords, and number of agents for each swarm on the server.

### 2. Inspect a swarm by name

Authorized user-agents can inspect a specific, existing swarm by name on a MAIL server via the `mail` command `swarm-get`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={ua_jwt}
uv run mail swarm-get {swarm_name}
```

If a swarm with the specified name exists, its description, keywords, and full list of agents will be printed to the console.

### 3. Create a swarm as an admin

Authorized admins can create a new swarm on a MAIL server via the `mail-admin` CLI command `swarm-post`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={admin_jwt}
uv run mail-admin swarm-post {swarm_name} {swarm_description}
```

The arguments `swarm_name` and `swarm_description` are required. Optionally, the swarm's `keywords` can be specified as well:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={admin_jwt}
uv run mail-admin swarm-post {swarm_name} {swarm_description} \
--keywords "kw-1" "kw-2"
```

If this operation was successful, information on the new swarm will be printed to the console.

### 4. Delete a swarm as an admin

Authorized admins can delete an existing swarm by name on a MAIL server via the `mail-admin` command `swarm-delete`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={admin_jwt}
uv run mail-admin swarm-delete {swarm_name}
```

If this operation was successful, information on the newly-deleted swarm will be printed to the console.

## Source Material

- `src/mail/client/src/mail_client/commands/swarm_list.py`
- `src/mail/client/src/mail_client/commands/swarm_get.py`
- `src/mail/client/src/mail_client/commands/swarm_post.py`
- `src/mail/client/src/mail_client/commands/swarm_delete.py`
- `src/mail/server/src/mail_server/routers/swarms.py`
- `src/mail/server/src/mail_server/routers/admin.py`
