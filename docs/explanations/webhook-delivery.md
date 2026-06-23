# Webhook Delivery

Status: draft

## Scope

How MAIL notifies external consumers when mail is delivered: the event
shape, the security model, the retry behavior, and the assumptions the
contract places on receivers.

This document is for implementers building a webhook consumer (a
service that receives MAIL events and routes them somewhere else).
The matching how-to for *registering* webhooks via the admin API is
[Manage Webhooks](../howtos/manage-webhooks.md); the matching tutorial
for *building* a receiver end-to-end is [Build a Webhook
Receiver](../tutorials/build-webhook-receiver.md).

## What webhooks are for

The MAIL inbox is the durable surface: mail lives there, indexed by
recipient, and any authenticated user-agent can poll it via the
inbox endpoints. Webhooks are a *push* alternative: when a message
is delivered to a recipient's inbox, the MAIL server fires an HTTP
`POST` to one or more registered URLs with a structured payload, so
downstream services can react without polling.

Webhooks do not replace the inbox. The inbox is the source of truth.
A webhook that fails to deliver is a notification missed; the message
itself is still readable by the recipient via the normal inbox API.
This shapes the security and retry contract below.

## Event types

The only `event` value in v2 is `mail.delivered`. A future release
may add other event types; receivers should reject events whose
`event` field they do not recognize, but should not fail registration
on the presence of an unknown event in the `events` array (the
`/admin/webhooks` validator already gates that).

## Payload shape

Every `mail.delivered` event is delivered as a JSON request body
shaped like:

```json
{
  "event": "mail.delivered",
  "event_id": "evt_<uuid>",
  "delivered_at": "2026-06-24T19:31:00.000000+00:00",
  "message": {
    "message_id": "msg_<uuid>",
    "reply_to": null,
    "sender": "alice@chorus@example.com",
    "recipient": "bob@chorus@example.com",
    "subject": "Daily briefing",
    "body": "…",
    "tags": [],
    "sent_at": "2026-06-24T19:30:55.123456+00:00",
    "swarm": "chorus",
    "metadata": {}
  }
}
```

Field notes:

- `event_id` is unique per delivery attempt SET but is reused across
  retries (see [Retries](#retries)). Receivers MUST treat
  `event_id` as the dedup key — a webhook receiver that processes
  the same `event_id` more than once is a bug.
- `message_id` is prefixed with `msg_`. The bare UUID is stored on
  the canonical `MAILMessage`; the prefix is added at webhook
  payload construction time. Use the prefixed form when fetching the
  full message via the inbox API.
- `reply_to`, when set, is the prefixed `message_id` of the original
  message this is replying to.
- `tags` is a list of slug-shaped strings the sender attached.
- `metadata.list_address`, when present, indicates the delivery
  originated from a list expansion. Use it to surface the originating
  list to the end-recipient.

Refer to [Data Models](../references/data-models.md) for the full
field-by-field schema of the inner `MAILMessageInWebhook`.

## Security model

### Why HMAC

MAIL emits webhooks to URLs configured by an administrator. The
receiver needs to verify that an incoming request actually came from
MAIL (not from a third party who guessed or scanned the URL). The
shared mechanism is an HMAC signature over the request body, computed
with a secret known only to MAIL and the receiver.

### What gets signed

MAIL computes the signature as:

```
signature = HMAC-SHA256(secret, f"{timestamp}.{raw_body}")
```

Where:

- `timestamp` is the value of the `X-MAIL-Timestamp` header (Unix
  seconds since the epoch, as a string).
- `raw_body` is the *exact byte sequence* of the request body. MAIL
  signs `payload.model_dump_json()` (Pydantic's canonical JSON
  serialization) and posts those same bytes as the request body.
  Re-encoding via `json=...` would produce different bytes (different
  key order, whitespace, type coercion) and break verification.

The `secret` is the value supplied when the webhook was registered.

### Headers sent on every webhook POST

| Header             | Value                                             |
| ------------------ | ------------------------------------------------- |
| `Content-Type`     | `application/json`                                |
| `X-MAIL-Event-Id`  | The `event_id` from the payload.                  |
| `X-MAIL-Timestamp` | Unix seconds since epoch, as a string.            |
| `X-MAIL-Signature` | `sha256=<hex>` where `<hex>` is the HMAC digest.  |
| `User-Agent`       | `Multi-Agent-Interface-Layer-Server/2.0.0 (...)` |

### Receiver verification

A correct receiver does the following on every request:

1. Read `X-MAIL-Timestamp` and reject the request (`408` or `400`)
   if it is more than 5 minutes from the receiver's clock. This
   bounds the replay window.
2. Read `X-MAIL-Signature` and strip the `sha256=` prefix.
3. Recompute `HMAC-SHA256(secret, f"{timestamp}.{raw_body}")` over
   the raw request body bytes (NOT the parsed JSON).
4. Compare to the received digest using a constant-time comparison.
   Reject (`403`) if they differ.
5. Read `X-MAIL-Event-Id` and check it against a recent-events store.
   If it has been processed in the last ~24 hours, return `200` with
   a no-op response (the request is a retry; the original processing
   stands).
6. Process the event. Return `200` (or `202`) on success.

Step 5 is where the dedup contract lives. MAIL retries on transient
failure (see below) and reuses the same `event_id` across retries.
A receiver that does not dedup will process the same delivery
multiple times under load or after any transient outage.

### What if the secret isn't configured

A receiver that has registered a webhook but does not yet have the
secret in its environment SHOULD reject incoming requests with
`503 Service Unavailable` (not `403`). `403` would suggest a real
authentication failure; `503` correctly signals "I'm not ready,
please retry."

## Retries

MAIL fires up to **six attempts** per event, with the following
delays between attempts:

| Attempt | Delay before this attempt | Cumulative wall-clock |
| ------- | ------------------------- | ---------------------- |
| 1       | (immediate)               | 0                      |
| 2       | 1 second                  | ~1 s                   |
| 3       | 30 seconds                | ~31 s                  |
| 4       | 5 minutes                 | ~5 min                 |
| 5       | 1 hour                    | ~1 h                   |
| 6       | 6 hours                   | ~7 h                   |

After the sixth attempt, MAIL gives up. The total retry window is
roughly **7 hours and 31 seconds** from the first attempt.

A retry is triggered when `_webhook_delivered_post` returns `True`,
which happens for any of:

- `httpx.TimeoutException` on the request.
- A `5xx` status code from the receiver.
- A `429 Too Many Requests` status code.

A retry is NOT triggered (and the event is considered delivered or
abandoned) for:

- A `2xx` status code (success).
- A `4xx` status code other than `429` (the receiver explicitly
  rejected the request; retries won't change that).

### Implications for receivers

- A receiver that needs to throttle MAIL's webhook firing should
  return `429` rather than starve. MAIL backs off cleanly.
- A receiver that detects a permanently malformed payload should
  return `4xx` (not `5xx`). MAIL will not retry, which is the
  correct behavior — the next event will succeed.
- A receiver should NOT return `5xx` for "I couldn't route this
  internally but I have the message stored." That makes MAIL retry
  unnecessarily. Instead, return `200` — MAIL's inbox is the source
  of truth; the routing failure does not need MAIL's help to
  recover.

## The "inbox is source of truth" contract

This is the single most important assumption a receiver makes:

> If a webhook delivery fails, the message is not lost. The
> recipient can still poll their MAIL inbox via the regular HTTP
> API. The webhook is a notification — its failure shapes UX, not
> correctness.

In practice this means:

- A receiver that successfully verifies the signature, accepts the
  event_id as new, but then fails internally while processing the
  event SHOULD STILL RETURN `200`. The event is recorded as
  processed; the internal failure is the receiver's problem to
  recover from (it can read the message from the MAIL inbox on its
  own schedule).
- A receiver MUST NOT return `5xx` to "force MAIL to retry." MAIL's
  retries are for transport failures, not for receiver-internal
  bugs. The retry schedule above is short enough that downstream
  systems can fail and recover quickly without webhook help.

## Reliability and ordering

The webhook contract guarantees:

- **At-least-once delivery** within the 7-hour retry window. After
  retries exhaust, the message is still in the recipient's inbox
  and can be fetched there.
- **Per-event idempotency via `event_id`.** Receivers MUST dedup on
  `event_id` to handle retries correctly.

The contract does NOT guarantee:

- **Ordering.** Webhooks for related events (e.g., several mails to
  the same recipient in rapid succession) may arrive out of order
  due to retry interleavings or concurrent firing. Receivers MUST
  treat each event independently. The `sent_at` and `delivered_at`
  timestamps can be used to reconstruct ordering if needed.
- **Exactly-once delivery.** Dedup by `event_id` collapses the
  at-least-once delivery to at-most-once *processing* in the
  receiver's domain, but MAIL itself can fire the same event_id up
  to six times.
- **Synchronous delivery.** Webhook firing happens asynchronously
  on the MAIL server. A successful `POST /drafts/{id}/send` (or
  similar) does not block on webhook delivery.

## See also

- [Manage Webhooks](../howtos/manage-webhooks.md) — registering,
  inspecting, and deleting webhooks via the admin API.
- [Build a Webhook Receiver](../tutorials/build-webhook-receiver.md)
  — step-by-step tutorial walking through the signature
  verification, dedup, and processing of a real receiver.
- [Delivery Model](delivery-model.md) — broader context on how MAIL
  routes a message from sender to recipient inbox.
- [Security Model](security-model.md) — the broader auth and
  authorization model the webhook contract sits within.
- [Data Models](../references/data-models.md) — formal field-by-field
  schemas for `MAILWebhook`, `MAILMessageInWebhook`, and the
  envelope.
- [HTTP API](../references/http-api.md) — the formal route list,
  including the webhook firing target shape and the admin
  registration endpoints.
