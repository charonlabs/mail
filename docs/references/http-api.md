# HTTP API

Status: stub

## Scope

Describe the HTTP API exposed by the MAIL server, with endpoints, auth
requirements, request bodies, response bodies, and error behavior.

## Source of Truth

- `spec/openapi.yaml`
- `src/mail/server/src/mail_server/server.py`
- `src/mail/server/src/mail_server/routers/`
- `src/mail/server/docs/reference/http.md`

## Entries to Cover

- Root and health endpoints.
- Authentication endpoints.
- Swarms.
- Inbox, outbox, drafts, and trash.
- Daemon endpoints.
- Admin endpoints.
- Mailing list endpoints.
- Common status codes and validation errors.

## Maintenance Notes

Prefer generated OpenAPI details for schemas and parameters. Keep handwritten
text focused on navigation and important implementation notes.
