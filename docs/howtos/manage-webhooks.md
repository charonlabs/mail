# Manage Webhooks

Status: draft

## Goal

How to register, inspect, update, and delete webhook subscriptions on
a MAIL server using the admin API. Webhooks let downstream services
receive `mail.delivered` events without polling — see [Webhook
Delivery](../explanations/webhook-delivery.md) for the conceptual
contract.

## Starting Point

You have admin credentials for the MAIL server, and you know the
public URL the webhook should fire against. You have a shared secret
already agreed with the receiver, or you're prepared to generate one.

## Steps

### 1. Generate a secret (if you don't already have one)

Webhook signatures use an HMAC-SHA256 with a shared secret. The
secret must be known to both MAIL and the receiver, and not exposed
elsewhere. A reasonable generator:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save the resulting string in a secure location accessible to the
receiver process. The receiver loads it from a config file or env
var; MAIL stores it on the registered webhook record.

### 2. Register the webhook

`POST /admin/webhooks` with the receiver URL, the events to
subscribe to, and the secret. v2 supports one event type
(`mail.delivered`); future versions may add more.

```bash
ADMIN_TOKEN="$(cat ~/.mail/admin.token)"
SECRET="…"  # from step 1

curl -sS -X POST "$MAIL_SERVER/admin/webhooks" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$(jq -n \
        --arg url "https://my-receiver.example.com/mail/webhook" \
        --arg secret "$SECRET" \
        '{url: $url, events: ["mail.delivered"], secret: $secret}')"
```

A successful response returns the new webhook record (including its
generated `webhook_id`):

```json
{
  "webhook": {
    "webhook_id": "wh_abc12345-…",
    "url": "https://my-receiver.example.com/mail/webhook",
    "events": ["mail.delivered"],
    "secret": "…"
  },
  "metadata": {}
}
```

Save the `webhook_id` — you'll need it to inspect, update, or delete
the registration later. The secret is also stored in MAIL's backend;
the receiver only needs its own copy.

### 3. List all registered webhooks

`GET /admin/webhooks` returns the IDs of every webhook on the
server:

```bash
curl -sS "$MAIL_SERVER/admin/webhooks" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

```json
{
  "webhook_ids": ["wh_abc12345-…", "wh_def67890-…"],
  "metadata": {}
}
```

To get the full record for a specific webhook, use
`GET /admin/webhooks/{webhook_id}`:

```bash
curl -sS "$MAIL_SERVER/admin/webhooks/wh_abc12345-…" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 4. Update an existing webhook

`PATCH /admin/webhooks/{webhook_id}` can change the receiver URL or
rotate the secret. The webhook_id and the subscribed events are
immutable; to change events you must delete and re-register.

```bash
curl -sS -X PATCH "$MAIL_SERVER/admin/webhooks/wh_abc12345-…" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://new-receiver.example.com/mail/webhook", "secret": "new-secret"}'
```

When rotating a secret, coordinate with the receiver so both sides
update at the same moment; otherwise webhooks delivered between the
two updates will fail signature verification on the receiver side.

### 5. Delete a webhook

`DELETE /admin/webhooks/{webhook_id}` removes the registration. MAIL
will stop firing webhooks to that URL immediately.

```bash
curl -sS -X DELETE "$MAIL_SERVER/admin/webhooks/wh_abc12345-…" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

In-flight retries for events that were already being delivered when
the webhook was deleted are not interrupted; if a retry attempt
succeeds, the receiver still gets the event. After the retry
schedule exhausts (or succeeds), no further events fire.

## Validation

After registering a webhook, you can confirm it works end-to-end by:

1. Sending a test message to a recipient on the server.
2. Watching the receiver's logs for an incoming `POST` with the
   expected event_id, signature, and payload.
3. Confirming the receiver returns `200`. (A non-2xx response will
   trigger MAIL's retry ladder; see [Webhook
   Delivery](../explanations/webhook-delivery.md#retries).)

## See also

- [Webhook Delivery](../explanations/webhook-delivery.md) — the
  contract MAIL emits and the receiver must verify.
- [Build a Webhook Receiver](../tutorials/build-webhook-receiver.md)
  — implementer's tutorial for writing a receiver from scratch.
- [HTTP API](../references/http-api.md) — full route and response
  reference.
