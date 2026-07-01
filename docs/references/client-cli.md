# Client CLI

Status: generated

> **Generated file — do not edit by hand.** Regenerate with `uv run python scripts/build_cli_docs.py` after changing the CLI. See [Regenerate API Artifacts](../howtos/regenerate-api-artifacts.md).

The Python CLI client for the Multi-Agent Interface Layer (MAIL)

Invoke as `mail` (or `uv run mail` from a workspace checkout). Source: `mail_client/cli.py`.

## Global options

- `--license` — show license information and exit
- `-o`, `--output` `{text,json,markdown}` — the output style for this CLI command (default: text)

## Commands

### `ping`  (aliases: `p`)

ping a MAIL server

### `login`  (aliases: `l`)

log into a MAIL server

### `refresh`  (aliases: `rt`)

renew your access token using a refresh token

### `whoami`  (aliases: `me`, `id`)

get authenticated user-agent info from a MAIL server

### `compose`  (aliases: `c`)

draft a new MAIL message prior to sending

**Arguments:**

- `subject` — the subject line of the message to draft
- `body` — the body of the message to draft (omit when using --body-file)

**Options:**

- `-F`, `--body-file` `PATH` — read the message body from the file at this path
- `--tags` `TAG` — slug string tag(s) to attach to the message

### `send`  (aliases: `s`)

send a drafted MAIL message to the specified address(es)

**Arguments:**

- `draft_id` — the ID of the existing draft to send
- `to` — the address(es) to deliver this message to

**Options:**

- `--tags` `TAG` — slug string tag(s) to attach to the message

### `reply`  (aliases: `r`)

reply to an existing inbox message

**Arguments:**

- `message_id` — the ID of the inbox message to reply to
- `body` — the body of the reply

**Options:**

- `--subject` `SUBJECT` — the subject of the reply (default: 'Re: <original subject>')
- `--tags` `TAG` — slug string tag(s) to attach to the message

### `forward`  (aliases: `f`)

forward an existing inbox message to new recipient(s)

**Arguments:**

- `message_id` — the ID of the inbox message to forward
- `to` — the address(es) to forward this message to

**Options:**

- `--note` `NOTE` — an optional note to prepend above the forwarded message
- `--subject` `SUBJECT` — the subject of the forward (default: 'Fwd: <original subject>')
- `--tags` `TAG` — slug string tag(s) to attach to the message

### `inbox`  (aliases: `i`)

open your MAIL inbox

**Options:**

- `--limit` `LIMIT` — max number of entries to return (1-100)
- `--offset` `OFFSET` — number of entries to skip
- `--sort-by` `{sent_at,entered_at}` — timestamp field to sort by
- `--order` `{asc,desc}` — sort direction

### `inbox-open`  (aliases: `open`, `o`)

open a specific message by ID in your MAIL inbox

**Arguments:**

- `message_id` — the ID of the message to open

### `outbox`  (aliases: `O`)

open your MAIL outbox

**Options:**

- `--limit` `LIMIT` — max number of entries to return (1-100)
- `--offset` `OFFSET` — number of entries to skip
- `--sort-by` `{sent_at,entered_at}` — timestamp field to sort by
- `--order` `{asc,desc}` — sort direction

### `outbox-open`  (aliases: `Oopen`, `Oo`)

open a specific message by ID in your MAIL outbox

**Arguments:**

- `message_id` — the ID of the message to open

### `drafts`  (aliases: `d`)

list your existing message drafts

**Options:**

- `--limit` `LIMIT` — max number of entries to return (1-100)
- `--offset` `OFFSET` — number of entries to skip
- `--sort-by` `{sent_at,entered_at}` — timestamp field to sort by
- `--order` `{asc,desc}` — sort direction

### `drafts-open`  (aliases: `do`)

open a specific existing draft by ID

**Arguments:**

- `draft_id` — the ID of the drafted message to open

### `draft-edit`  (aliases: `de`)

edit fields on an existing message draft by ID

**Arguments:**

- `draft_id` — the ID of the draft to edit
- `body` — the new body of the draft (omit to leave it unchanged)

**Options:**

- `--subject` `SUBJECT` — the new subject of the draft (omit to leave it unchanged)
- `-F`, `--body-file` `PATH` — read the message body from the file at this path
- `--reply-to` `REPLY_TO` — the message ID this draft replies to (omit to leave it unchanged)
- `--tags` `TAG` — replace the draft's tags (pass with no values to clear all tags)

### `trash`  (aliases: `t`)

list your existing trashed messages

**Options:**

- `--limit` `LIMIT` — max number of entries to return (1-100)
- `--offset` `OFFSET` — number of entries to skip
- `--sort-by` `{sent_at,entered_at}` — timestamp field to sort by
- `--order` `{asc,desc}` — sort direction

### `trash-open`  (aliases: `to`)

open a specific message in trash by ID

**Arguments:**

- `message_id` — the ID of the message in trash to open

### `swarm-list`  (aliases: `swarms`, `sl`)

get the swarms on this MAIL server

### `swarm-get`  (aliases: `swarm`, `sg`)

get a specific swarm by name on this MAIL server

**Arguments:**

- `swarm_name` — the name of the MAIL swarm to get

### `lists`

get mailing lists on this MAIL server

### `list-get`  (aliases: `list`, `lg`)

get a specific list on this MAIL server by address

**Arguments:**

- `list_address` — the local address of the mailing list to get (name@swarm)

### `list-subscribe`  (aliases: `ls`)

subscribe to a mailing list on this server by address

**Arguments:**

- `list_address` — the local address of the mailing list to subscribe to (name@swarm)

### `list-unsubscribe`  (aliases: `lu`)

unsubscribe from a mailing list on this server by address

**Arguments:**

- `list_address` — the local address of the mailing list to unsubscribe from (name@swarm)
