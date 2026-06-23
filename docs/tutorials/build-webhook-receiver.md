# Build a Webhook Receiver

Status: draft

## Goal

Walk through building a correct MAIL webhook receiver from scratch.
By the end you'll have a small HTTP server that verifies signatures,
dedupes retries, and processes `mail.delivered` events.

The companion explainer is [Webhook
Delivery](../explanations/webhook-delivery.md). This tutorial assumes
you've read it; we'll reference its sections rather than restate the
contract.

## Prerequisites

- A running MAIL server you can register webhooks against (see
  [Run a Local MAIL](run-local-mail.md)).
- Python 3.12+ with `fastapi`, `uvicorn`, and `httpx`.
- A receiver URL MAIL can reach. For local development, a tunnel
  (e.g., `cloudflared`) or both processes on the same host both
  work.

## The receiver, end to end

We'll build a single-file FastAPI app that:

1. Accepts `POST /mail/webhook`.
2. Verifies the `X-MAIL-Timestamp`, `X-MAIL-Signature`, and the
   `Content-Type`.
3. Dedupes against `X-MAIL-Event-Id`.
4. Parses the payload, then prints a one-line summary.

### Set up

Create a new directory and install the dependencies:

```bash
mkdir mail-receiver && cd mail-receiver
uv init
uv add fastapi uvicorn
```

### The signature verification function

The signature scheme is documented in detail in [Webhook Delivery →
Security model](../explanations/webhook-delivery.md#security-model).
The receiver's job is to recompute `HMAC-SHA256(secret,
f"{timestamp}.{raw_body}")` over the *raw bytes* it received (not
the parsed JSON), then compare in constant time.

```python
import hashlib
import hmac


def verify_signature(
    *, raw_body: bytes, timestamp: str, signature: str, secret: str
) -> bool:
    """
    Return True iff ``signature`` is a valid HMAC-SHA256 over
    ``f"{timestamp}.{raw_body}"`` keyed by ``secret``.

    Signature comes in as ``"sha256=<hex>"``; strip the prefix before
    comparison.
    """
    if not signature.startswith("sha256="):
        return False
    received = signature[len("sha256=") :]

    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=f"{timestamp}.".encode("utf-8") + raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received, expected)
```

A common bug at this step is to recompute the HMAC over the *parsed
and re-serialized* JSON body, which produces different bytes than
the originally-signed body and breaks verification. Always operate
on the raw bytes you received on the wire.

Another common bug is to forget the `f"{timestamp}."` prefix. The
signed message is `timestamp.body`, not just `body`.

### Dedup against event_id

MAIL retries on transient failures (see [Retries](../explanations/webhook-delivery.md#retries))
and reuses the same `event_id` for every attempt. A correct
receiver remembers recently-processed event_ids and short-circuits
duplicates. For this tutorial, an in-memory set is enough:

```python
from collections import deque
from datetime import datetime, timezone

PROCESSED_EVENTS: deque[tuple[str, datetime]] = deque(maxlen=10_000)


def is_duplicate(event_id: str) -> bool:
    """
    Return True iff ``event_id`` has already been processed.
    Garbage-collects entries older than 24 hours on each call.
    """
    now = datetime.now(timezone.utc)
    # Drop expired entries from the left.
    while PROCESSED_EVENTS and (now - PROCESSED_EVENTS[0][1]).total_seconds() > 86400:
        PROCESSED_EVENTS.popleft()
    return any(e[0] == event_id for e in PROCESSED_EVENTS)


def mark_processed(event_id: str) -> None:
    PROCESSED_EVENTS.append((event_id, datetime.now(timezone.utc)))
```

For production use, replace this with a real durable store (SQLite,
Redis, a database table) so dedup survives restarts. The 24-hour
window matches MAIL's retry exhaustion behavior with a safety
margin.

### Timestamp skew window

Reject any request whose `X-MAIL-Timestamp` is more than 5 minutes
from the receiver's clock. This bounds the replay window and catches
clock-drift bugs early.

```python
import time

SKEW_WINDOW_SECONDS = 5 * 60


def is_timestamp_in_window(timestamp: str) -> bool:
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    return abs(int(time.time()) - sent_at) <= SKEW_WINDOW_SECONDS
```

### The full receiver

```python
import os

from fastapi import FastAPI, HTTPException, Request

SECRET = os.environ.get("MAIL_WEBHOOK_SECRET")

app = FastAPI()


@app.post("/mail/webhook")
async def mail_webhook(request: Request) -> dict[str, object]:
    if SECRET is None:
        # Not configured yet. Tell MAIL to retry later.
        raise HTTPException(
            status_code=503, detail="Webhook secret not configured."
        )

    timestamp = request.headers.get("X-MAIL-Timestamp")
    signature = request.headers.get("X-MAIL-Signature")
    event_id = request.headers.get("X-MAIL-Event-Id")

    if not timestamp:
        raise HTTPException(status_code=400, detail="Missing X-MAIL-Timestamp.")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing X-MAIL-Signature.")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing X-MAIL-Event-Id.")

    if not is_timestamp_in_window(timestamp):
        raise HTTPException(status_code=408, detail="Timestamp outside skew window.")

    raw_body = await request.body()

    if not verify_signature(
        raw_body=raw_body, timestamp=timestamp, signature=signature, secret=SECRET
    ):
        raise HTTPException(status_code=403, detail="Invalid signature.")

    if is_duplicate(event_id):
        return {"status": "duplicate", "event_id": event_id}

    import json

    payload = json.loads(raw_body)
    message = payload["message"]

    # Process the event. For this tutorial, just print.
    print(
        f"[mail.delivered] {message['sender']} → {message['recipient']}: "
        f"{message['subject']}"
    )

    mark_processed(event_id)
    return {"status": "ok", "event_id": event_id}
```

Run it with:

```bash
MAIL_WEBHOOK_SECRET="<from registration>" uv run uvicorn receiver:app --port 8000
```

### Register with MAIL

In another shell, register the receiver per [Manage
Webhooks](../howtos/manage-webhooks.md):

```bash
curl -sS -X POST "$MAIL_SERVER/admin/webhooks" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:8000/mail/webhook",
       "events": ["mail.delivered"],
       "secret": "<same secret as MAIL_WEBHOOK_SECRET>"}'
```

### Send a test message

Send a message to any recipient on the MAIL server. The receiver
should log:

```
[mail.delivered] alice@chorus@example.com → bob@chorus@example.com: Hello
```

If nothing arrives:

- Check the MAIL server logs for outgoing POST attempts. A `403`
  back from your receiver usually means the secret strings don't
  match.
- Check that `MAIL_WEBHOOK_SECRET` in the receiver's env matches
  the secret you registered exactly (no extra whitespace).
- Verify the receiver is reachable from MAIL's host (e.g., curl
  from the MAIL host to your receiver URL).

## What this tutorial leaves out

- **Durable dedup.** Replace the in-memory set with a real store
  before deploying.
- **Internal routing.** This receiver just prints. In production,
  you'd route the event to whatever downstream service needs it
  (a chat surface, a database write, a queue, etc.).
- **The "inbox is source of truth" contract.** If your internal
  routing fails after signature verification succeeds, return
  `200` anyway — the message lives in the MAIL inbox and your
  service can recover on its own. See [Webhook Delivery → The
  "inbox is source of truth"
  contract](../explanations/webhook-delivery.md#the-inbox-is-source-of-truth-contract).
- **Observability.** Log every received event, every failed
  signature, every dedup hit. Webhook receivers are silent failure
  modes if you don't.

## See also

- [Webhook Delivery](../explanations/webhook-delivery.md) — the
  contract this tutorial implements.
- [Manage Webhooks](../howtos/manage-webhooks.md) — registering and
  rotating webhooks via the admin API.
- [HTTP API](../references/http-api.md) — formal route reference.
