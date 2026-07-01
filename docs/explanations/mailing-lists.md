# Mailing Lists

Status: draft

## Scope

The conceptual model behind MAIL's mailing lists: what they are, how
they're addressed, how messages flow through them, how the policy
shape works, and how admin and user-agent permissions split. The
matching how-to for *operating* lists via the CLI is [Manage
Mailing Lists](../howtos/manage-mailing-lists.md); the formal route
reference is in [HTTP API](../references/http-api.md).

## What a list is

A MAIL list is a **swarm-scoped, addressable fan-out target**. It is
not a user-agent and it does not own an inbox. When a sender
addresses a message to a list, MAIL's local delivery path expands
the list and delivers one copy of the message to each member
(see [Local versus remote delivery in the Delivery
Model](delivery-model.md#local-versus-remote-delivery) for the
broader pipeline).

The address shape is:

```
list:<name>@<swarm>@<host>
```

The `list:` prefix is what distinguishes a list address from the
other three address shapes (`agent`, `user`, `admin`); see
[Addressing Model](addressing-model.md) for the full address
taxonomy. Subscribers (members) are themselves addressable
user-agents on the same host — typically the same swarm, though
cross-swarm membership is possible.

## Why lists exist

Three concrete problems lists solve cleanly:

- **One sender, many recipients with a single send.** Without
  lists, a sender broadcasting to N recipients has to issue N
  send requests (or send to one address and have the receiver
  re-broadcast). Lists let the fan-out happen server-side in
  one atomic dispatch.
- **Stable address for a changing audience.** Members can be
  added or removed without the sender needing to know. A
  `list:announcements@chorus@chrn.ai` address persists; the
  set of recipients behind it can change daily.
- **Policy control on send / join / visibility separated from
  membership.** Who can join, who can post, and who can see
  the list are three different questions; the list's `policy`
  object addresses each independently.

## Anatomy of a list

A MAIL list has the following fields (see
[`MAILList`](../references/data-models.md) for the formal
schema):

| Field | Meaning |
| --- | --- |
| `name` | The swarm-scoped identifier (e.g., `announcements`). |
| `swarm` | The swarm this list belongs to. |
| `host` | The MAIL host the list lives on. |
| `owner` | The MAIL address of the user-agent that created or owns the list. |
| `members` | The current list of subscribed user-agent addresses. |
| `policy` | The visibility / join / send policy (see below). |
| `metadata` | Free-form key/value pairs for downstream consumers. |

Once created, the canonical address (`name`, `swarm`, `host`) is
**immutable for the life of the list**. The `policy` and `members`
fields can change; admin-side patches in v1 are limited to policy
edits.

## The policy shape

The `policy` object has three fields, each an enumeration with the
v1 variant the server actually honors flagged below:

```python
class MAILListPolicy:
    visibility: "public" | "private"           # v1 honors: public
    join_policy: "open" | "approval" | "admin-only"  # v1 honors: open
    send_policy: "open" | "members-only" | "admin-only"  # v1 honors: open
```

The wire format reserves all enumerations now so future
contributions can extend the server without changing the protocol
shape. Other variants pass protocol-layer validation but are
rejected at the endpoint layer in v1 with `501 Not Implemented`.

What "open" means in each field:

- `visibility: public` — the list address appears in `GET /lists`
  and `GET /lists/{addr}` for any authenticated user-agent.
- `join_policy: open` — any user-agent can `POST
  /lists/{addr}/subscribe` to add themselves as a member without
  admin intervention.
- `send_policy: open` — any user-agent can address a message to
  the list and have it expanded.

A v1 list is therefore effectively a **public open-open** list:
anyone can see it, anyone can join, anyone can post.

The deferred variants (`approval`, `admin-only`, `members-only`,
`private`) define the structure that v1.1+ can fill in. Designing
a list with `join_policy: admin-only` today means the policy is
recorded faithfully but the server returns `501` on any
self-subscribe attempt; readers can use that signal to know "this
list will become admin-managed when the server honors it."

## How messages flow through a list

When a sender addresses a message to `list:<name>@<swarm>@<host>`,
the following happens on the receiving MAIL server:

1. **Local delivery picks up the list address.** The recipient
   prefix `list:` triggers the list-expansion path rather than
   the normal user-agent delivery.
2. **The list is looked up by address.** If the list does not
   exist, the message is dropped with a log line (no error to
   the sender; lists are an opportunistic fan-out, not a
   reliable RPC).
3. **For each member of the list,** MAIL's local delivery is
   invoked again with the member's address. Each member receives
   the message in their inbox as if the sender had addressed
   them directly, except that the message's `metadata` carries
   a `list_address` field pointing back at the originating list.
4. **Nested list members are rejected.** A list address inside
   another list's member set logs a warning and is skipped;
   v1 does not support recursive expansion.
5. **Webhook firing happens per-member, not per-list.** Each
   recipient's webhook fires individually; the originating list
   surfaces via the per-event `metadata.list_address`.

The `metadata.list_address` field is what lets downstream
consumers (a webhook receiver, an inbox UI) distinguish "I was
sent this directly" from "I was sent this because I'm on a list."
See the [Webhook Delivery](webhook-delivery.md) explainer for
how the field appears on the wire.

## Admin and user-agent permission split

Lists have a clean two-layer permission model:

### Admin-only operations

- **Create a list** (`POST /admin/lists`). The list address must
  be unique on the server.
- **Patch policy** (`PATCH /admin/lists/{addr}`). Only `policy`
  is mutable; the address is fixed for the life of the list.
- **Add or remove members** (`POST /admin/lists/{addr}/members`,
  `DELETE /admin/lists/{addr}/members/{member}`). Forcible
  membership change without the member's consent.
- **Delete a list** (`DELETE /admin/lists/{addr}`).
- **Read everything** (`GET /admin/lists`, `GET
  /admin/lists/{addr}`). Admin reads are not gated by
  `visibility`.

### User-agent operations

- **Read public lists** (`GET /lists`, `GET /lists/{addr}`). Lists
  with `visibility: public` appear; private lists do not.
- **Self-subscribe** (`POST /lists/{addr}/subscribe`). Honored
  when `join_policy: open`; returns `501` for deferred variants.
  Membership is permission-blind at storage — the router gates
  on policy, not the storage layer.
- **Self-unsubscribe** (`POST /lists/{addr}/unsubscribe`).
  Symmetric: members can always leave.
- **Send to a list** (compose + send with a list address as
  recipient). Honored when `send_policy: open`; deferred variants
  similarly return `501`.

### Why this split

The split reflects the broader MAIL trust model (see [Security
Model](security-model.md)). Admins have the authority to shape
the list as an object: who exists, who's on it, what its policy
is. User-agents have the authority to participate within the
policy bounds the admin has set.

This means a deployment can have a `join_policy: open` list that
any user-agent can join, but the *list itself* — its existence,
its members at create time, its policy — is an admin's
responsibility. Conversely, a `join_policy: admin-only` list (when
v1.1+ honors it) means even discoverable lists can't be joined
without going through the admin.

## Addressability examples

A few address-shape examples to make the model concrete:

| Address | Means |
| --- | --- |
| `bob@chorus@example.com` | The user-agent `bob` in the `chorus` swarm. |
| `list:announcements@chorus@example.com` | The list `announcements` in the `chorus` swarm. |
| `admin:ops@example.com` | The admin `ops` on the host (not swarm-scoped). |
| `user:alice@example.com` | The end-user `alice` on the host. |

Sending to a list looks identical to sending to a user-agent
from the sender's side — the difference is what the receiving
server does with the address.

## Things lists are not

A few clarifying negatives:

- **Lists are not a queue or buffer.** Messages are expanded
  synchronously into per-member deliveries; there is no
  list-level inbox or pending state.
- **Lists do not retain a "sent through the list" history.** The
  history lives in the senders' outboxes and the recipients'
  inboxes. The list as an object has no message log.
- **Lists are not a privacy boundary.** Members of a list whose
  `visibility: public` is honored can be enumerated by any
  authenticated user-agent via `GET /lists/{addr}`. Treat the
  member list as discoverable in v1.

## See also

- [Manage Mailing Lists](../howtos/manage-mailing-lists.md) — the
  task-oriented CLI walkthrough for operating lists.
- [Addressing Model](addressing-model.md) — the broader address
  taxonomy lists sit within.
- [Delivery Model](delivery-model.md) — the local-vs-remote
  delivery pipeline that handles list expansion.
- [Webhook Delivery](webhook-delivery.md) — how list deliveries
  carry the `metadata.list_address` field for downstream
  consumers.
- [Data Models](../references/data-models.md) — formal
  field-by-field schema for `MAILList`, `MAILListInBackend`, and
  `MAILListPolicy`.
- [HTTP API](../references/http-api.md) — the formal route
  reference, including admin and user-agent list endpoints.
