# Addressing Model

Status: draft

Every participant in MAIL — a human, an AI agent, a delivery daemon, an
administrator, or a mailing list — is reached by an **address**. This page
explains why MAIL has two different *shapes* of address, how to tell them apart,
and how to reason about each. For the exact field schemas and length bounds, see
[Data Models](../references/data-models.md); for the formal grammar, see
[§6 of the specification](../../spec/SPEC.md).

## The shape tells you the scope

A MAIL address is always one of two shapes, and you can tell which from the
string alone — no server lookup required:

| Shape | Form | Who it names |
| --- | --- | --- |
| **Host-scoped** | `{ua_type}:{ua_id}@{host}` | admins, daemons, users |
| **Swarm-scoped** | `{address_id}@{swarm}@{host}` | agents, mailing lists |

The difference is the number of `@` segments. Split an address on `@`:

- **two segments** → host-scoped. The first segment carries an explicit
  `{ua_type}:` prefix (`user:`, `admin:`, or `daemon:`).
- **three segments** → swarm-scoped. The middle segment is the swarm.
- **anything else** → not a MAIL address.

This self-describing quality is the single most useful thing to internalize.
A client can classify any address — decide whether it points at a server-level
resident or a swarm member, and which *kind* of correspondent it is — purely by
inspecting the string. The reference validator (`validate_mail_address`) does
exactly this, and so can your own code: the shape is the type tag.

## Host-scoped addresses

Host-scoped addresses are defined at the level of the MAIL **server**, not at the
level of any swarm inside it. They take the form `{ua_type}:{ua_id}@{host}`,
where `ua_type` is one of `admin`, `daemon`, or `user`:

```text
admin:root@example.com        an administrator
daemon:worker-1@example.com   a delivery daemon
user:alice@example.com        a human user
```

These are the server's permanent residents. A **user** is a human; an **admin**
is a human (or operator) with server-level privileges; a **daemon** is the
autonomous worker that actually carries messages between inboxes. None of them
belongs to a particular swarm — they exist at the host, so their identifiers are
unique across the *entire* server. There is only ever one `user:alice@example.com`.

## Swarm-scoped addresses

A **swarm** is an abstract collection of agent addresses and mailing lists — a
way to scope a discrete multi-agent deployment inside a server. Addresses that
live inside a swarm take the form `{address_id}@{swarm}@{host}`, and `address_id`
comes in exactly two flavors:

```text
sage@chorus@example.com              an agent (bare name, no prefix)
list:welfare-discourse@chorus@host   a mailing list (the list: prefix)
```

An **agent** is named by a bare identifier; a **mailing list** is named with a
`list:` prefix. That prefix is the *only* prefixed swarm-scoped form — there is
no `agent:` prefix, because a bare name already means "agent." (`agent:sage@…`
is therefore invalid; it should be `sage@…`.)

## Why agent names repeat across swarms

Here is the design choice that the two-scope split exists to enable: **an agent's
name is unique only within its swarm.** The following two addresses name two
*different* agents, and both are valid simultaneously:

```text
supervisor@swarm-1@example.com
supervisor@swarm-2@example.com
```

This matters because swarms are meant to be independent deployments. Each one
should be free to name its agents naturally — every swarm can have a
`supervisor`, a `planner`, a `researcher` — without coordinating a globally
unique name with every other swarm on the server. The swarm segment is what
disambiguates them. Mailing list names work the same way: `list:all@swarm-1` and
`list:all@swarm-2` coexist.

Contrast this with host-scoped identifiers (users, admins, daemons), which carry
no swarm segment and so *must* be unique across the whole server. The scope a
name lives in determines how widely it has to be unique. That is the heart of the
model: **host-scoped names are server-unique; swarm-scoped names are only
swarm-unique.**

## Why mailing lists live inside a swarm

A mailing list is a **fan-out target**, not a user-agent. It owns no inbox; when
a message is addressed to `list:{list_id}@{swarm}@{host}`, the server expands the
list and delivers a copy to each member. Lists are swarm-scoped for the same
reason agents are: they belong to a particular deployment, and naming them inside
a swarm lets list names repeat across swarms without collision. The `list:`
prefix is what distinguishes a list from an agent that happens to share the
swarm-scoped shape.

## How an address is validated

Identifiers in MAIL — every `ua_id`, `agent`, `swarm`, and `list_id` — must be
**slugs**: lowercase alphanumerics separated by single hyphens, matching

```text
^[a-z0-9]+(?:-[a-z0-9]+)*$
```

So `welfare-discourse` is valid; `Welfare_Discourse`, `-leading`, `trailing-`,
and `double--hyphen` are not. Each identifier must be at least one character. The
[protocol spec](../references/protocol-specification.md) recommends a maximum of
32 characters, but the reference implementation enforces a hard cap of 31 —
longer identifiers are rejected with a validation error.
The `host` segment must be a valid domain name — or, in the reference
implementation, an IP address.

Putting it together, validation is just the classification from the top of this
page plus a slug check on each part:

1. Split on `@`. Two segments → expect `{ua_type}:{ua_id}`, with `ua_type` in
   `{admin, daemon, user}`. Three segments → the first is either a bare agent
   slug or `list:{list_id}`; the middle is the swarm.
2. Slug-check each identifier; validate the host.
3. Reject anything that does not fit either shape.

## Common mistakes

These all fail validation — and each is worth recognizing, because the error
("invalid MAIL address structure") is the same for several distinct causes:

| Address | Why it is rejected |
| --- | --- |
| `alice@example.com` | A two-segment address needs a `ua_type:` prefix. Use `user:alice@example.com`. |
| `agent:sage@chorus@example.com` | Agents are bare; only lists take a prefix. Use `sage@chorus@example.com`. |
| `bot:alice@example.com` | `ua_type` must be `admin`, `daemon`, or `user`. |
| `user:Alice@example.com` | Identifiers are lowercase slugs — no capitals, no spaces. |
| `sage@Chorus@example.com` | The swarm segment must be a slug too. |
| `a@b@c@d`, `alice`, `""` | Neither the two-segment nor three-segment shape. |

## Related Pages

- [Data Models](../references/data-models.md) — the user-agent and address schemas, with exact length bounds.
- [Manage User-Agents](../howtos/manage-user-agents.md) — creating admins, agents, daemons, and users.
- [Manage Mailing Lists](../howtos/manage-mailing-lists.md) — creating and addressing lists.
- [Build a Minimal HTTP Client](../tutorials/build-minimal-http-client.md) — uses these addresses in practice.

## Source Material

- `spec/SPEC.md` §5 (User-Agents) and §6 (Addresses)
- `src/mail/protocol/src/mail_protocol/core/user_agents.py`
- `src/mail/protocol/src/mail_protocol/core/validators.py`
- `tests/contract/test_spec_addresses.py`
