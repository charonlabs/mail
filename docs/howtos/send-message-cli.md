# Send a Message with the CLI

Status: draft

## Goal

Compose a draft and send it to one or more recipients with the `mail` CLI.

## Starting Point

You have a valid `MAIL_TOKEN` for a user-agent allowed to send (see
[Authenticate a User-Agent](authenticate-user-agent.md)), and a daemon is running
so the message can be delivered (see [Run the MAIL Daemon](run-daemon.md)).
Sending is a two-step draft-then-send flow — see
[Delivery Model](../explanations/delivery-model.md).

## Steps

### 1. Compose a draft

A draft holds only a subject and body; recipients come later. Provide the body
inline or read it from a file with `-F`/`--body-file`:

```bash
MAIL_SERVER={server_url}
MAIL_TOKEN={ua_jwt}
uv run mail compose "Status update" "The batch job finished cleanly."
```

The console prints the new draft, including its **draft ID** (a UUID). You can
attach `--tags` (slug strings) that carry onto the sent message.

### 2. Capture the draft ID

Note the `draft_id` from the output; you can also list drafts with
`uv run mail drafts` or open one with `uv run mail drafts-open {draft_id}`.

### 3. Send the draft to one or more recipients

Recipients are supplied at send time. Pass the draft ID followed by one or more
addresses:

```bash
uv run mail send {draft_id} supervisor@default@localhost user:alice@localhost
```

The console prints the assembled message with a **message ID** distinct from the
draft ID.

### 4. Inspect the outbox

```bash
uv run mail outbox                       # list your sent messages
uv run mail outbox-open {message_id}     # open one
```

A `null` delivery time means *sent, awaiting delivery*; once the daemon delivers,
the outbox entry records the delivering daemon.

### 5. Inspect the recipient inbox

With the recipient's token (and a running daemon), confirm arrival:

```bash
MAIL_TOKEN={recipient_jwt} uv run mail inbox
MAIL_TOKEN={recipient_jwt} uv run mail open {message_id}
```

### 6. Handle validation failures

Malformed input is rejected before the message is created or delivered: a bad
subject/body fails at compose time, and a malformed recipient address fails at
send time with a `422` whose `detail` explains the problem. Recipient addresses
must be valid MAIL addresses — see [Addressing Model](../explanations/addressing-model.md).

## See also

- [Authenticate a User-Agent](authenticate-user-agent.md)
- [Delivery Model](../explanations/delivery-model.md)
- [Client CLI](../references/client-cli.md) — full command reference.

## Source Material

- `src/mail/client/src/mail_client/commands/compose.py`
- `src/mail/client/src/mail_client/commands/send.py`
