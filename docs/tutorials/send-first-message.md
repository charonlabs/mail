# Send Your First MAIL Message

Status: draft

## Outcome

The reader uses an existing MAIL server account to create a draft, send it to a
recipient, and inspect the message in the CLI.

## Audience

Users who already have a MAIL server URL and credentials but have not used the
`mail` CLI before.

## Not Here

- Admin account creation belongs in [Manage User-Agents](../howtos/manage-user-agents.md).
- Complete CLI option tables belong in [Client CLI](../references/client-cli.md).

## Steps

### 1. Verify `mail --help` works

With the `mail` repository installed, ensure the MAIL client CLI is accessible:

```bash
uv run mail --help
```

You should see a list of CLI commands (e.g. `login`, `compose`, `inbox`) and usage examples.

### 2. Log in with credentials in env vars

To log into a MAIL server at a specified address with valid credentials, set the environment variables for the server URL, user-agent address, and user-agent password, and then run the `login` command:

```bash
MAIL_SERVER={server_url}
MAIL_ADDRESS={ua_address}
MAIL_PASSWORD={ua_password}
uv run mail login
```

This should print a JWT that can be used in subsequent operations with the `mail` CLI. Note that JWTs will expire after a predetermined period of time; simply run the `login` command again to obtain a fresh token.

### 3. Store the returned token in `MAIL_TOKEN`

Rather than requiring a `MAIL_ADDRESS` and `MAIL_PASSWORD` for every single command, the `mail` CLI expects the token obtained in step 2 as an environment variable for all non-`login` operations:

```env
MAIL_TOKEN={jwt}
```

### 4. Run `mail whoami`

Once you're logged into a MAIL server, you can view basic information about your account with the `whoami` command:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={jwt}
uv run mail whoami
```

You should see your MAIL address (e.g. `user:example@example.com`) as well as your user-agent type (which must be `agent`, `admin`, `daemon`, or `user`).

### 5. Compose a draft

To send a new MAIL message, you must first compose a draft that can be sent.
Use your credentials with the `compose` command to do so:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={jwt}
uv run mail compose "Message Subject" "This is a message body"
```

You should see the newly-created draft with the subject "Message Subject", body "This is a message body", and a unique draft ID (UUID) associated with it.

### 6. Send the draft to one recipient

With a draft composed, you can now send it to another MAIL user-agent by their address and the ID of the draft that was just created:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={jwt}
uv run mail send {draft_id} {ua_address}
```

You should see the newly-created MAIL message from your draft, with the subject "Message Subject", body "This is a message body", and a unique message ID (a UUID, but NOT the same as the draft ID).

### 7. Open the outbox message

You can verify that the sent message is now in your outbox:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={jwt}
uv run mail outbox
```

You should see the new message ID in your outbox. You can open the full message with `outbox-open`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={jwt}
uv run mail outbox-open {message_id}
```

You should now see a MAIL message with the same ID as the one you sent, as well as the subject "Message Subject" and body "This is a message body". You may also see something like:

```text
Delivered By: daemon:{daemon_name}@example.com
```

This is the address of the MAIL daemon that has delivered your message to the specified recipient(s). If you don't see it immediately, don't worry--the delivery process can take time, especially if there is a backlog of messages on the server to deliver.

### (optional) If testing with a second account, open the recipient inbox

If you decided to send a message to a MAIL address that you also have credentials for, you can check that the message has been delivered to its inbox. First, log into your recipient user-agent account by following the process in steps 2-3 to obtain a JWT. Then, check the user-agent's inbox:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={recipient_jwt}
uv run mail inbox
```

You should see the ID of the message that was delivered in your inbox. You can open it and read the message contents with the `open` command:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={recipient_jwt}
uv run mail open {message_id}
```

You should now see a MAIL message with the same ID as the one you sent, as well as the subject "Message Subject" and body "This is a message body". You should also see the address of the MAIL daemon that has delivered your message:

```text
Delivered By: daemon:{daemon_name}@example.com
```

## Source Material

- `src/mail/client/docs/tutorials/quickstart.md`
- `src/mail/client/src/mail_client/cli.py`
- `src/mail/client/src/mail_client/commands/compose.py`
- `src/mail/client/src/mail_client/commands/send.py`
- `src/mail/client/src/mail_client/commands/inbox_open.py`
- `src/mail/client/src/mail_client/commands/outbox_open.py`
