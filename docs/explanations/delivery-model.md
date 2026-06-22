# Delivery Model

Status: draft

In MAIL, **sending a message is not the same as delivering it.** When a
user-agent sends, the message is written to the server and placed in the sender's
outbox — but it is not yet in anyone's inbox. A separate, authorized worker (a
*daemon*) carries it the rest of the way. This page explains why MAIL splits
those two acts, how the hand-off works, and what it means operationally. For the
hands-on version of the first half, see
[Build a Minimal HTTP Client](../tutorials/build-minimal-http-client.md); for the
formal contract, see [§8 of the specification](../../spec/SPEC.md).

## Sending is not delivering

The central idea is a deliberate separation:

1. **Send** — the sender writes a message to the server. It lands in the sender's
   outbox, marked as not-yet-delivered, and its id is queued for delivery.
2. **Deliver** — a daemon later picks the message up and the server files a copy
   into each recipient's inbox.

So a message has two observable states — *sent* and *delivered* — and MAIL makes
the gap between them explicit rather than hiding it. Everything below follows
from taking that separation seriously.

## Two steps to a message: draft, then send

Creating a message is itself two steps, which is worth understanding before
delivery enters the picture:

- **Create a draft** (`POST /drafts`) with only a `subject` and a `body`. A draft
  has no recipients.
- **Send the draft** (`POST /drafts/{draft_id}/send`) with the `recipients`. This
  is the moment the `MAILMessage` is assembled — a fresh `message_id`, the
  sender, the recipients, the subject and body, a `sent_at` timestamp — stored in
  the sender's outbox with no delivery stamp yet, and enqueued for delivery.

Recipients are bound at *send* time, not at draft time, so a draft is a reusable
subject-and-body that can be sent more than once or to different addresses. (The
draft remains in your drafts box after sending.) For why recipients are addressed
the way they are, see [Addressing Model](addressing-model.md).

## The delivery buffer

The server keeps a **delivery buffer**: the list of `message_id`s awaiting
delivery. Sending a draft enqueues its id there. The buffer holds *ids*, not
copies — the message itself lives in storage and in the sender's outbox; the
buffer is just the server's "still needs carrying" worklist.

## The daemon carries the mail

A **daemon** is a distinct user-agent whose entire job is delivery. The spec
constrains it tightly: a daemon MUST NOT alter the messages it carries, and
SHOULD NOT compose messages of its own. Delivery is a narrow, privileged,
auditable role — not something every agent does for itself.

A daemon authenticates exactly like any other user-agent (password grant → bearer
token), and the server verifies that the caller really is a daemon before
honoring delivery calls. It then runs a simple loop (the reference daemon pauses
~30 seconds between iterations):

```text
sender                server                         daemon
  │  POST /drafts/{id}/send                            │
  │ ───────────────────▶ store in outbox               │
  │                      enqueue id in buffer          │
  │                                                    │
  │                      ◀───── POST /daemon/message-buffer/clear
  │                      return pending ids,           │
  │                      empty the buffer ──────────▶  │
  │                                                    │
  │                      ◀───── POST /daemon/deliver/local {ids}
  │                      for each id:                  │
  │                        file copy into each inbox   │
  │                        stamp outbox delivered_at,  │
  │                        delivered_by = daemon       │
  │                      return delivered summaries ─▶ │
```

In other words: clearing the buffer hands the daemon the pending ids *and* empties
the buffer; the delivery call is where the server actually files copies into
recipients' inboxes and stamps the sender's outbox entry with the delivery time
and the delivering daemon's address.

## Sent versus delivered, made observable

Because delivery is a separate step, MAIL exposes where a message is in its
journey. Each outbox entry carries two nullable fields:

- `delivered_at` — `null` while the message is still waiting; a timestamp once a
  daemon has carried it.
- `delivered_by` — the address of the daemon that delivered it.

A `null` `delivered_at` means *sent, awaiting delivery*; a populated one means
*delivered*. The recipient's inbox entry likewise records which daemon delivered
it. This is the surface a client uses to show a message's status honestly —
"Sent" versus "Delivered by `daemon:…`" — rather than pretending the two are the
same. (Delivery is also where the server can fire webhooks so recipients are
notified of new mail rather than having to poll; see [HTTP API](../references/http-api.md).)

## Local versus remote delivery

The implemented delivery path is **local**: `POST /daemon/deliver/local` carries
messages between user-agents on the *same* server. A second endpoint,
`POST /daemon/deliver/remote`, is reserved for future delivery of messages that
arrive from other MAIL servers; it is not yet implemented. For now, treat
delivery as a within-host operation.

## Pre-send versus post-send errors

MAIL draws a sharp line between failures that happen *before* a message is
accepted and failures that happen *after*:

- **Pre-send errors (§8.1)** are synchronous and caught at create or send time. A
  malformed subject or body means the message is never created; a malformed
  recipient address means it is never delivered. The sender is told immediately,
  as a `4xx` response (a validation failure returns `422` with a `detail`
  explaining what was wrong). Nothing is queued.
- **Post-send errors (§8.2)** happen after a valid message is in the system. If a
  daemon cannot deliver it, the message MUST be preserved and the daemon SHOULD
  log the error. These failures are asynchronous and recoverable — the message is
  not lost.

The boundary is the useful thing to remember: before send, an error is the
sender's to fix and the message may not exist at all; after send, the message is
durable and getting it delivered is the daemon's responsibility.

## Operational implications

- **Decoupling.** A sender never blocks on a recipient, or even on a daemon being
  online. Sending is just a write. If no daemon is connected, messages simply wait
  in the buffer (and sit undelivered in the outbox) until one runs.
- **Latency.** The reference daemon polls on an interval (~30 seconds by
  default), so delivery is prompt but not instantaneous — expect up to a poll
  interval of lag, especially under a backlog.
- **Observability.** Track delivery through the outbox (`delivered_at` /
  `delivered_by`) and the daemon's logs. The daemon also warns when the number of
  ids it cleared does not match the number the server reports as delivered.
- **Durability and retries.** Messages are stored server-side and preserved on
  delivery failure (§8.2). Note the shape of the loop, though: clearing the buffer
  empties it, so once a daemon has claimed a batch, delivering it is that daemon's
  responsibility. Run a reliable daemon and watch its logs rather than assuming
  failed items are automatically re-queued.
- **The unit of delivery is the `message_id`.** The daemon hands the server a
  batch of ids to deliver; idempotency and retry policy live at that granularity.

## Related Pages

- [Build a Minimal HTTP Client](../tutorials/build-minimal-http-client.md) — performs the draft → send half over raw HTTP.
- [Run the MAIL Daemon](../howtos/run-daemon.md) — running the daemon that does the carrying.
- [Addressing Model](addressing-model.md) — how recipients are named.
- [Daemon CLI](../references/daemon-cli.md) and [HTTP API](../references/http-api.md) — the daemon commands and `/daemon` endpoints.

## Source Material

- `spec/SPEC.md` §7 (Messages) and §8 (Delivery)
- `src/mail/server/src/mail_server/routers/daemon.py`
- `src/mail/daemon/src/mail_daemon/maild/api.py`
- `src/mail/server/src/mail_server/backends/base.py` (and `backends/memory/api.py` for the reference behavior)
- `tests/integration/test_flows.py`
