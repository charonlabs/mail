# Manage Mailing Lists

Status: draft

## Goal

How to create mailing lists, inspect them, manage subscriptions or
members, edit policy, and delete them. The conceptual model — the
address shape, the policy structure, the admin/user permission
split — is in [Mailing Lists](../explanations/mailing-lists.md);
this how-to assumes you've at least skimmed it.

## Starting Point

The reader has credentials with permissions appropriate for the list
action. Admin credentials are required for create / patch / member
add-remove / delete; user-agent credentials are sufficient for
read / subscribe / unsubscribe / send.

Two address forms appear below, and the CLI is strict about which it
wants — see [Addressing Model](../explanations/addressing-model.md):

- **List-management commands** (`list-get`, `list-subscribe`,
  `list-unsubscribe`, `list-member-post`, `list-member-delete`,
  `list-delete`) take the **local** `{name}@{swarm}` form (e.g.
  `announcements@chorus`). The server resolves it to the list's
  canonical `list:{name}@{swarm}@{host}` address using its own host.
- **Sending to a list** (step 8) names the list as a message
  recipient, so it uses the **full** routable form
  `list:{name}@{swarm}@{host}` (e.g.
  `list:announcements@chorus@example.com`), just like any other
  recipient.

This how-to writes `{list_address}` for the local management form and
`{list_recipient}` for the full send form.

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

### 6. Update list policy as an admin

Policy is the only mutable part of a list — the canonical address
(`name`, `swarm`, `host`) is immutable. The server exposes
`PATCH /admin/lists/{name}@{swarm}` accepting an `AdminListPatchRequest`
body (a single optional `policy` object).

> **Not yet available from the CLI.** The `mail-admin list-patch`
> command is registered but currently a stub: it declares no
> arguments and its handler raises `NotImplementedError`
> (`src/mail/client/src/mail_client/commands/list_patch.py`). Until it
> is implemented, patch a list's policy by calling the endpoint
> directly — for example with `curl` (the path takes the **local**
> `{name}@{swarm}` form):

```bash
curl -s -X PATCH "$MAIL_SERVER/admin/lists/announcements@chorus" \
  -H "Authorization: Bearer $MAIL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"policy":{"visibility":"public","join_policy":"open","send_policy":"open"}}'
```

For v1, only `public` / `open` / `open` are honored; the other
variants are reserved in the wire format and rejected at the
endpoint layer with `501`. See [Mailing
Lists](../explanations/mailing-lists.md#the-policy-shape) for
context on the deferred variants.

### 7. Delete a list as an admin

To remove an existing list entirely, use `list-delete`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={admin_jwt}
uv run mail-admin list-delete {list_address}
```

The list is removed from the server and the canonical address
becomes available for re-creation. In-flight messages already
expanded into per-member deliveries before the delete are
unaffected (they live in the recipients' inboxes); messages
addressed to the list after the delete are dropped per the
unknown-list path described in [Mailing Lists → How messages
flow through a list](../explanations/mailing-lists.md#how-messages-flow-through-a-list).

### 8. Send a message to a list address

If they are authorized to do so, user-agents can send a message to a
list by naming the list as a recipient of the `mail` command `send`.
Because this is a message recipient (not a management target), use the
**full** routable form `list:{name}@{swarm}@{host}` here — written
`{list_recipient}` below:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={ua_jwt}
uv run mail send {draft_id} {list_recipient}
```

The receiving server expands the list and delivers one copy to
each member's inbox. Each member's webhook (if any) fires with a
`metadata.list_address` field naming the originating list so
downstream consumers can distinguish list deliveries from direct
ones — see [Webhook
Delivery](../explanations/webhook-delivery.md#payload-shape) for
the field placement on the wire.

## See also

- [Mailing Lists](../explanations/mailing-lists.md) — the
  conceptual model: address shape, policy fields, expansion
  semantics, permission split.
- [Webhook Delivery](../explanations/webhook-delivery.md) — how
  list deliveries surface to webhook receivers via
  `metadata.list_address`.
- [Addressing Model](../explanations/addressing-model.md) — the
  full address taxonomy lists sit within.
- [HTTP API](../references/http-api.md) — the formal route
  reference for admin and user-agent list endpoints.

## Source Material

- `src/mail/client/src/mail_client/commands/lists.py`
- `src/mail/client/src/mail_client/commands/list_post.py`
- `src/mail/client/src/mail_client/commands/list_subscribe.py`
- `src/mail/client/src/mail_client/commands/list_member_post.py`
- `src/mail/server/src/mail_server/routers/lists.py`
- `src/mail/protocol/src/mail_protocol/core/lists.py`
