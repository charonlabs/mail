# Build a Minimal HTTP Client

Status: draft

## Outcome

You will talk to a MAIL server using nothing but HTTP — no `mail` CLI — and walk
away with a small shell script that authenticates, confirms your identity,
creates a draft, sends it, and reads the server's responses. The same handful of
calls translate directly into any language's HTTP library.

## Audience

Developers integrating MAIL into their own tools and services who want to speak
to the server directly over HTTP rather than shelling out to the `mail` CLI.
Comfort with `curl` and JSON is assumed.

## Not Here

- Full endpoint listings belong in [HTTP API](../references/http-api.md).
- Protocol motivation belongs in [MAIL v2 Overview](../explanations/mail-v2-overview.md).
- Why sending is a two-step (draft, then send) is covered in [Delivery Model](../explanations/delivery-model.md).

## Prerequisites

- A running MAIL server plus a user-agent address and password. If you do not
  have one, complete [Run MAIL Locally](run-local-mail.md) first — this tutorial
  reuses its `admin:dummy@localhost` account and `http://127.0.0.1:8865` server.
- `curl` to make requests, and `jq` to read and extract JSON. (`jq` is only for
  convenience; every call works without it.)

Set these in your shell once — every step below uses them:

```bash
export MAIL_SERVER="http://127.0.0.1:8865"
export MAIL_ADDRESS="admin:dummy@localhost"
export MAIL_PASSWORD="<the admin password from Run MAIL Locally>"
```

## Steps

### 1. Confirm the server is reachable

Before authenticating, verify the server is up. The health endpoint needs no token:

```bash
curl -s "$MAIL_SERVER/health"
```

```json
{"status":"ok"}
```

(`GET /` returns the protocol name, version, and uptime if you want to confirm
the version you are targeting.)

### 2. Obtain a bearer token

MAIL uses the OAuth2 "password" flow, so credentials are sent as **form fields**,
not as a JSON body:

```bash
curl -s -X POST "$MAIL_SERVER/auth/token" \
  -d "grant_type=password" \
  --data-urlencode "username=$MAIL_ADDRESS" \
  --data-urlencode "password=$MAIL_PASSWORD"
```

The response carries a JSON Web Token:

```json
{"access_token":"eyJhbGciOiJIUzI1NiIs...","token_type":"bearer","refresh_token":"...","expires_in":1800,"metadata":{}}
```

`expires_in` is the access-token lifetime in seconds. For an *interactive
principal* — a user or admin, as with the `admin` account used here —
`refresh_token` is populated (agents and daemons receive `refresh_token: null`
and re-authenticate with their credentials). This tutorial only needs
`access_token`; renewing via the refresh token is out of scope here.

Capture the token so the authenticated calls can reuse it:

```bash
export MAIL_TOKEN=$(curl -s -X POST "$MAIL_SERVER/auth/token" \
  -d "grant_type=password" \
  --data-urlencode "username=$MAIL_ADDRESS" \
  --data-urlencode "password=$MAIL_PASSWORD" | jq -r .access_token)
```

Tokens expire after the server's configured lifetime (`MAIL_JWT_EXPIRE_MINUTES`).
When a call starts returning `401`, request a fresh token the same way.

### 3. Confirm your identity

Every authenticated request carries the token in an `Authorization: Bearer`
header. Use `whoami` to check that the token works and to see who the server
thinks you are:

```bash
curl -s "$MAIL_SERVER/auth/whoami" -H "Authorization: Bearer $MAIL_TOKEN" | jq
```

The user-agent is nested one level inside the response envelope:

```json
{
  "user_agent": {
    "user_agent": {
      "ua_type": "admin",
      "admin_id": "dummy",
      "host": "localhost"
    }
  },
  "metadata": {}
}
```

`ua_type` is one of `agent`, `user`, `admin`, or `daemon`, and the remaining
fields depend on it — an `agent`, for instance, carries `name`, `swarm`, and
`host` instead of `admin_id`. See [Addressing Model](../explanations/addressing-model.md)
for how these compose into a full address.

### 4. Create a draft

A draft holds only a `subject` and a `body`; recipients are chosen later, at send
time. Send the draft as JSON:

```bash
curl -s -X POST "$MAIL_SERVER/drafts" \
  -H "Authorization: Bearer $MAIL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Hello over HTTP","body":"My first MAIL message, sent with curl."}' | jq
```

The new draft comes back wrapped in an `entry`:

```json
{
  "entry": {
    "draft": {
      "draft_id": "0f8e6e2a-1c4d-4a9b-8e7f-2b6c1d0a9f3e",
      "subject": "Hello over HTTP",
      "body": "My first MAIL message, sent with curl.",
      "created_at": "2026-06-16T23:11:00Z",
      "updated_at": null
    },
    "sent_at": null,
    "sent_by": null
  },
  "metadata": {}
}
```

Capture the `draft_id` for the next step:

```bash
export DRAFT_ID=$(curl -s -X POST "$MAIL_SERVER/drafts" \
  -H "Authorization: Bearer $MAIL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Hello over HTTP","body":"My first MAIL message, sent with curl."}' \
  | jq -r .entry.draft.draft_id)
```

### 5. Send the draft

Choose one or more recipient addresses and send the draft. The recipients are
supplied now, not at draft time:

```bash
curl -s -X POST "$MAIL_SERVER/drafts/$DRAFT_ID/send" \
  -H "Authorization: Bearer $MAIL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"recipients":["supervisor@default@localhost"]}' | jq
```

The response is the assembled message. It has a `message_id` distinct from the
`draft_id`, plus the recipients you just chose:

```json
{
  "message": {
    "mail_version": "2.0",
    "message_id": "5a2c1b9d-7e3f-4c8a-9d21-0b4e6f8a1c2d",
    "reply_to": null,
    "sender": "admin:dummy@localhost",
    "recipients": ["supervisor@default@localhost"],
    "subject": "Hello over HTTP",
    "body": "My first MAIL message, sent with curl.",
    "tags": [],
    "sent_at": "2026-06-16T23:11:05Z",
    "metadata": {}
  },
  "metadata": {}
}
```

The server has now stored the message; a running daemon delivers a copy to each
recipient's inbox. (MAIL stores first and delivers via daemon — see
[Delivery Model](../explanations/delivery-model.md). To watch the message land,
follow the inbox steps in [Run MAIL Locally](run-local-mail.md).)

### 6. Read success and error payloads

Two conventions make every response predictable:

- **Success** responses wrap their payload and always include a `metadata`
  object. A single resource uses a key like `entry` or `message`; list endpoints
  (such as `GET /drafts`) use `entries`.
- **Errors** return a non-2xx status and a JSON object with a `detail` string.
  Always check the status code — a parser that only reads the body can miss the
  failure.

Print the status code alongside the body with `-w`. An invalid or missing token
returns `401`:

```bash
curl -s -w "\n%{http_code}\n" "$MAIL_SERVER/auth/whoami" \
  -H "Authorization: Bearer not-a-real-token"
```

```text
{"detail":"could not validate credentials"}
401
```

A request that reaches the server but fails validation returns `422`, with
`detail` naming the offending field and the reason. For example, omitting the
required `body` when creating a draft:

```bash
curl -s -w "\n%{http_code}\n" -X POST "$MAIL_SERVER/drafts" \
  -H "Authorization: Bearer $MAIL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subject":"only a subject"}'
```

```text
{"detail":"request body validation failed: 1 validation error for DraftPostRequest\nbody\n  Field required ..."}
422
```

Sending to a malformed address, or with an empty `recipients` list, fails the
same way — the `detail` tells you which field and why.

### 7. Put it together: a minimal client

Every call above, assembled into one script. Save it as `mailclient.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

MAIL_SERVER="${MAIL_SERVER:-http://127.0.0.1:8865}"
MAIL_ADDRESS="${MAIL_ADDRESS:-admin:dummy@localhost}"
: "${MAIL_PASSWORD:?set MAIL_PASSWORD}"
recipient="${1:?usage: mailclient.sh <recipient-address>}"

# 1. authenticate
token=$(curl -s -X POST "$MAIL_SERVER/auth/token" \
  -d grant_type=password \
  --data-urlencode "username=$MAIL_ADDRESS" \
  --data-urlencode "password=$MAIL_PASSWORD" | jq -r .access_token)
auth=(-H "Authorization: Bearer $token")

# 2. confirm identity
echo "authenticated as: $(curl -s "${auth[@]}" "$MAIL_SERVER/auth/whoami" \
  | jq -r '.user_agent.user_agent.ua_type')"

# 3. create a draft
draft_id=$(curl -s -X POST "$MAIL_SERVER/drafts" "${auth[@]}" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Hello over HTTP","body":"Sent by mailclient.sh"}' \
  | jq -r .entry.draft.draft_id)
echo "draft created: $draft_id"

# 4. send it
message_id=$(curl -s -X POST "$MAIL_SERVER/drafts/$draft_id/send" "${auth[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"recipients\":[\"$recipient\"]}" \
  | jq -r .message.message_id)
echo "message sent:  $message_id"
```

Run it with a recipient address:

```bash
MAIL_PASSWORD="<admin password>" ./mailclient.sh supervisor@default@localhost
```

```text
authenticated as: admin
draft created: 0f8e6e2a-1c4d-4a9b-8e7f-2b6c1d0a9f3e
message sent:  5a2c1b9d-7e3f-4c8a-9d21-0b4e6f8a1c2d
```

That is a complete MAIL client in four calls — authenticate, identify, draft,
send. Port the same requests into your language's HTTP library, reuse the bearer
token across calls, and you have native MAIL integration with no dependency on
the CLI.

## Source Material

- `spec/openapi.yaml`
- `src/mail/protocol/src/mail_protocol/network/requests.py`
- `src/mail/protocol/src/mail_protocol/network/responses.py`
- `src/mail/server/src/mail_server/routers/auth.py`
- `src/mail/server/src/mail_server/routers/drafts.py`
