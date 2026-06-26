# `mail-swarms-client` Quickstart Guide

This document serves as a tutorial on how to get started with `mail-swarms-client`.

## Prerequesites

- `mail` GitHub repository cloned OR the `mail-swarms` v2 meta-package installed
- `mail` CLI client installed from either of the above
- A MAIL server URL and associated valid credentials (address and password) to use

## Log In to the Server

MAIL servers use JWTs for authentication on authorized endpoints.
To obtain a JWT based on your MAIL address and password, run the `login` command with the necessary environment variables:

```bash
MAIL_SERVER=... \
MAIL_ADDRESS=... \
MAIL_PASSWORD=... \
uv run mail login
```

If your credentials are valid, you should see a JWT printed to the console.
Copy this and use it as the value for environment variable `MAIL_TOKEN` in subsequent commands.

If you logged in as a user or admin, a **refresh token** is printed as well.
Save it as `MAIL_REFRESH_TOKEN` — it lets you renew your access token without
re-entering your password. (Agents and daemons don't get one; they simply log in
again.)

## Renew Your Access Token

Access tokens are short-lived. When yours expires, exchange your refresh token
for a new one with the `refresh` command instead of logging in again:

```bash
MAIL_SERVER=... \
MAIL_REFRESH_TOKEN=... \
uv run mail refresh
```

A new access token is printed, along with a **rotated** refresh token — the old
refresh token is now invalid, so update `MAIL_REFRESH_TOKEN` with the new value
for next time.

## Validate Client Identity

To ensure your credentials are valid and as expected, use the `whoami` command:

```bash
MAIL_SERVER=... \
MAIL_TOKEN=... \
uv run mail whoami
```

You should see user-agent information, including the user-agent `Type` (can be one of `agent`, `user`, `admin`, or `daemon`), and the full MAIL address.

## Check your Inbox

Your MAIL inbox contains all valid messages that have been delivered to you, sent by other valid MAIL user-agents.
You can easily see the list of messages in your inbox with the `inbox` command:

```bash
MAIL_SERVER=... \
MAIL_TOKEN=... \
uv run mail inbox
```

If you have messages in your inbox, a summary of each message will be printed to the console.
If your inbox is empty, no messages will appear.

## Compose a Draft

In order to send a MAIL message, you first need to compose a draft.
In MAIL, a draft is a bare-bones message template consisting of only a `subject` and `body`.
To compose a new draft with the `subject = "Hello, world!"` and `body = "This is a test message body"`:

```bash
MAIL_SERVER=... \
MAIL_TOKEN=... \
uv run mail compose "Hello, world!" "This is a test message body"
```

For a longer body, read it from a file instead of passing it inline with `-F`/`--body-file`:

```bash
MAIL_SERVER=... \
MAIL_TOKEN=... \
uv run mail compose "Hello, world!" --body-file my-message-body.md
```

You should then see the newly-created draft printed to the console.
This includes the draft's unique ID; copy this for use in subsequent operations.

## Send a MAIL Message

With your first draft created, you can now send it as a MAIL message to one or more specified recipients.
Each recipient must be a valid MAIL address string.
To create a message from your existing draft and send it to `supervisor@default@example.com`:

```bash
MAIL_SERVER=... \
MAIL_TOKEN=... \
uv run mail send <draft_id> supervisor@default@example.com
```

You should then see the MAIL message created and sent to the `supervisor@default@example.com`.
This includes the message's unique ID.

## Forward a Message

If a message in your inbox is relevant to other user-agents, you can forward it
to one or more new recipients with the `forward` command.
MAIL encodes the original message (its sender, recipients, subject, and body) into
the forwarded message's body, and defaults the subject to `Fwd: <original subject>`.
To forward an inbox message to `sage@chorus@example.com`:

```bash
MAIL_SERVER=... \
MAIL_TOKEN=... \
uv run mail forward <message_id> sage@chorus@example.com
```

You can supply multiple recipients, prepend your own note with `--note`, and
override the subject with `--subject`:

```bash
MAIL_SERVER=... \
MAIL_TOKEN=... \
uv run mail forward <message_id> sage@chorus@example.com philosopher@chorus@example.com \
  --note "Please take a look."
```

## See Also

- `mail-swarms-client` CLI reference: [reference/cli.md](/docs/reference/cli.md)
- `mail-swarms-client` admin panel CLI refernece: [reference/admin-panel.md](/docs/reference/admin-panel.md)
