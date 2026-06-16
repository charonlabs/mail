# Send a Message with the CLI

Status: stub

## Goal

How to compose a draft and send it to one or more MAIL recipients using the
`mail` CLI.

## Starting Point

The reader has a valid `MAIL_TOKEN` for a user-agent allowed to send messages.

## Source Material

- `src/mail/client/src/mail_client/commands/compose.py`
- `src/mail/client/src/mail_client/commands/send.py`
- `src/mail/client/docs/reference/cli.md`

## Steps to Cover

1. Compose a draft with subject and body.
2. Capture the draft ID.
3. Send the draft to one or more recipient addresses.
4. Inspect the outbox entry.
5. Inspect the recipient inbox when possible.
6. Handle malformed address or validation failures.

## Validation

The sender has an outbox message and the recipient can open the delivered inbox
message after daemon delivery.
