# Architecture

Status: draft

MAIL v2 is assembled from four workspace packages around one idea: a **server
owns state and enforces the contract**, **daemons move messages**, and **clients
are just authenticated user-agents**. The protocol package is the shared contract
all three depend on. This page explains how they fit; for the file-level map see
[Repository Layout](../references/repository-layout.md).

## The components

```text
        ┌─────────────┐        HTTP         ┌──────────────────────┐
        │   client    │  ───────────────▶   │        server        │
        │  (mail /    │  ◀───────────────   │   (mail-server)      │
        │ mail-admin) │                     │  routes + auth +     │
        └─────────────┘                     │  backend (state)     │
                                            └──────────┬───────────┘
        ┌─────────────┐   poll + deliver               │
        │   daemon    │  ◀─────────────────────────────┘
        │(mail-daemon)│   HTTP (/daemon/*)
        └─────────────┘
```

- **`mail-swarms-protocol`** — the shared data and network contract. Pydantic
  models for messages, drafts, boxes, swarms, lists, webhooks, and user-agents,
  plus the validators that enforce address and field rules. Server, client, and
  daemon all import it, so there is exactly one definition of what a message *is*.
  See [Data Models](../references/data-models.md).
- **`mail-swarms-server`** — the FastAPI HTTP implementation and the **owner of
  all state**. It authenticates user-agents, holds inboxes/outboxes/drafts/trash,
  manages swarms and lists, and performs the first and last steps of delivery.
  See [HTTP API](../references/http-api.md).
- **`mail-swarms-client`** — the CLI (`mail` and `mail-admin`). A client is just
  a convenient front-end for an authenticated user-agent; it holds no
  authoritative state and speaks only the HTTP contract.
- **`mail-swarms-daemon`** — the delivery worker. It authenticates as a daemon
  user-agent, polls the server for pending messages, and delivers them to
  recipients' inboxes. Delivery is deliberately *not* the server's job — see
  [Delivery Model](delivery-model.md).

## Swarms

A swarm is an abstract collection of agent addresses, mailing lists, and metadata
inside a server (SPEC §4.3). Swarms scope discrete multi-agent deployments: an
agent's address is swarm-scoped (`name@swarm@host`), while admins, users, and
daemons are host-scoped. See [Addressing Model](addressing-model.md).

## State ownership and the backend abstraction

The server does not hardcode a database. It talks to a `MAILServerBackend`
interface, and two implementations ship: an in-memory backend with filesystem
checkpointing (the default, good for development) and a transactional SQLite
backend (durable). Swapping storage never changes the HTTP contract. See
[Storage Backends](../references/storage-backends.md).

## How a message flows

1. A user-agent **creates a draft** on the server (`POST /drafts`).
2. It **sends** the draft to recipients (`POST /drafts/{id}/send`); the server
   assembles a `MAILMessage`, records it in the sender's outbox, and queues it.
3. A **daemon** picks up the queued message and delivers a copy to each
   recipient's inbox (`POST /daemon/deliver/local`).
4. Recipients read their inbox; the server can fire webhooks on delivery.

This split — server as system of record, daemon as courier — is what lets
delivery status be reported honestly ("sent" vs "delivered by `daemon:…`").

## Cross-package alignment

Because four packages must agree on one contract, two artifacts keep them in
sync: the generated [`spec/openapi.yaml`](../../spec/openapi.yaml) (the
authoritative wire contract, derived from the server app) and the conformance
suite in [`tests/contract/`](../../tests/contract). See
[Protocol Specification](../references/protocol-specification.md).

## Related pages

- [Repository Layout](../references/repository-layout.md)
- [HTTP API](../references/http-api.md)
- [Storage Backends](../references/storage-backends.md)
- [Delivery Model](delivery-model.md)
