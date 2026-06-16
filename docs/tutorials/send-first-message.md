# Send Your First MAIL Message

Status: stub

## Outcome

The reader uses an existing MAIL server account to create a draft, send it to a
recipient, and inspect the message in the CLI.

## Audience

Users who already have a MAIL server URL and credentials but have not used the
`mail` CLI before.

## Source Material

- `src/mail/client/docs/tutorials/quickstart.md`
- `src/mail/client/src/mail_client/cli.py`
- `src/mail/client/src/mail_client/commands/compose.py`
- `src/mail/client/src/mail_client/commands/send.py`
- `src/mail/client/src/mail_client/commands/inbox_open.py`
- `src/mail/client/src/mail_client/commands/outbox_open.py`

## Draft Outline

1. Verify `mail --help` works.
2. Log in with `MAIL_SERVER`, `MAIL_ADDRESS`, and `MAIL_PASSWORD`.
3. Store the returned token in `MAIL_TOKEN`.
4. Run `mail whoami`.
5. Compose a draft.
6. Send the draft to one recipient.
7. Open the outbox message.
8. If testing with a second account, open the recipient inbox.

## Not Here

- Admin account creation belongs in [Manage User-Agents](../howtos/manage-user-agents.md).
- Complete CLI option tables belong in [Client CLI](../references/client-cli.md).
