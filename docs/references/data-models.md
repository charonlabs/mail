# Data Models

Status: stub

## Scope

Describe active MAIL protocol Pydantic models and the validation rules that
shape request, response, and core data contracts.

## Source of Truth

- `src/mail/protocol/src/mail_protocol/core/`
- `src/mail/protocol/src/mail_protocol/network/`
- `src/mail/protocol/src/mail_protocol/core/validators.py`
- `spec/openapi.yaml`

## Entries to Cover

- User-agents.
- Addresses.
- Messages and message summaries.
- Drafts.
- Inboxes, outboxes, and trash.
- Swarms.
- Mailing lists.
- Webhooks.
- Request and response models.

## Maintenance Notes

Use field tables with type, required status, validation notes, and links to
source classes. Avoid duplicating generated OpenAPI schemas in full.
