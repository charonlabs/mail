# Manage Mailing Lists

Status: draft

## Goal

How to create mailing lists, inspect them, and manage subscriptions or members.

## Starting Point

The reader has credentials with permissions appropriate for the list action.

## Steps

### 1. List available mailing lists

MAIL user-agents can view all mailing lists visible to them by using the `mail` CLI command `lists` with valid credentials:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={ua_jwt}
uv run mail lists
```

This will print all list addresses visible to the authenticated user-agent to the console.

### 2. Inspect a list by address

User-agents can inspect a specific list (visible to them) by address through the `mail` command `list-get`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={ua_jwt}
uv run mail list-get {list_address}
```

If the specified list by address exists, its ID, owner, member user-agents, policies, and metadata will be printed to the console.

### 3. Create a list as an admin

To create a new mailing list on a MAIL server, use the `mail-admin` CLI client with valid admin credentials:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={admin_jwt}
uv run mail-admin list-post {list_name} {swarm_name} {list_owner}
```

Note that `list_name`, `swarm_name`, and `list_owner` are required arguments. You can optionally specify a list of MAIL user-agent addresses to add as members upon list creation:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={admin_jwt}
uv run mail-admin list-post {list_name} {swarm_name} {list_owner} \
--members "user:dummy@example.com" "supervisor@default@example.com"
```

### 4. Subscribe and unsubscribe as a user-agent

Non-`admin` user-agents may subscribe to or unsubscribe from mailing lists.
To subscribe to an existing mailing list by a given address, use the `mail` CLI client with authorized credentials:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={ua_jwt}
uv run mail list-subscribe {list_address}
```

If the operation was successful, details on the list subscribed to will be printed to the console.
To unsubscribe from an existing mailing list by a given address, use the `mail` CLI client with authorized credentials:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={ua_jwt}
uv run mail list-unsubscribe {list_address}
```

If the operation was successful, details on the list unsubscribed from will be printed to the console.

### 5. Add or remove members as an admin

Admins can add a MAIL user-agent by address to an existing mailing list with the `mail-admin` command `list-member-post`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={admin_jwt}
uv run mail-admin list-member-post {list_address} {member_address}
```

If successful, details on the mailing list will be printed to the console.

Similarly, admins can remove existing members by address from a mailing list with `list-member-delete`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={admin_jwt}
uv run mail-admin list-member-delete {list_address} {member_address}
```

If successful, details on the mailing list will be printed to the console.

### 6. Send a message to a list address

If they are authorized to do so, user-agents can send a message to a list address by specifying the list address in the `mail` command `send`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={ua_jwt}
uv run mail send {draft_id} {list_address}
```

## Source Material

- `src/mail/client/src/mail_client/commands/lists.py`
- `src/mail/client/src/mail_client/commands/list_post.py`
- `src/mail/client/src/mail_client/commands/list_subscribe.py`
- `src/mail/client/src/mail_client/commands/list_member_post.py`
- `src/mail/server/src/mail_server/routers/lists.py`
- `src/mail/protocol/src/mail_protocol/core/lists.py`
