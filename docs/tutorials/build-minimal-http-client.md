# Build a Minimal HTTP Client

Status: stub

## Outcome

The reader builds the smallest useful MAIL HTTP client: authenticate, call
`GET /auth/whoami`, create a draft, send it, and read response payloads.

## Audience

Developers integrating MAIL into tools that should not shell out to the `mail`
CLI.

## Source Material

- `spec/openapi.yaml`
- `src/mail/protocol/src/mail_protocol/network/requests.py`
- `src/mail/protocol/src/mail_protocol/network/responses.py`
- `src/mail/server/src/mail_server/routers/auth.py`
- `src/mail/server/src/mail_server/routers/drafts.py`

## Draft Outline

1. Start from a known server URL and credentials.
2. Obtain a bearer token from `POST /auth/token`.
3. Validate identity with `GET /auth/whoami`.
4. Create a draft with `POST /drafts/`.
5. Send the draft with `POST /drafts/{draft_id}/send`.
6. Parse success and validation errors.

## Not Here

- Full endpoint listings belong in [HTTP API](../references/http-api.md).
- Protocol motivation belongs in [MAIL v2 Overview](../explanations/mail-v2-overview.md).
