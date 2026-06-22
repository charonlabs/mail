# `mail-swarms-client` CLI Reference

This document serves as a reference to the `mail-swarms-client` CLI.

## Usage

```bash
mail [option]... <command> [argument]...
```

## Commands

### Core MAIL Operations

- `compose`: Draft a new MAIL message. The body may be passed inline or read from a file with `-F`/`--body-file PATH` (provide exactly one). Accepts `--tags TAG...` to attach slug tags.
- `send`: Send an existing draft by ID to the specified recipient(s). Accepts `--tags TAG...`, which are merged with the draft's tags.
- `reply`: Reply to an existing inbox message by ID. Addresses the reply to the original sender and defaults the subject to `Re: <original subject>`. Accepts `--subject SUBJECT` and `--tags TAG...`.
- `forward`: Forward an existing inbox message by ID to one or more new recipient(s). Encodes the original message (sender, recipients, subject, and body) into the forwarded body and defaults the subject to `Fwd: <original subject>`. Accepts `--note NOTE` to prepend a note above the forwarded message, plus `--subject SUBJECT` and `--tags TAG...`.
- `inbox`: Open your MAIL inbox.
- `inbox-open`: Open a specific message by ID in your MAIL inbox.
- `outbox`: Open your MAIL outbox.
- `outbox-open`: Open a specific message by ID in your MAIL outbox.
- `drafts`: List your existing MAIL message drafts.
- `drafts-open`: Open a specific existing draft by ID.
- `draft-edit`: Edit fields on an existing draft by ID. Accepts a new body inline or via `-F`/`--body-file PATH`, plus `--subject SUBJECT`, `--reply-to ID`, and `--tags TAG...` (pass `--tags` with no values to clear all tags). Omitted fields are left unchanged.
- `trash`: Open your MAIL trash box.
- `trash-open`: Open a specific message by ID in your MAIL trash box.

### Swarm Helpers

- `swarm-list`: List the MAIL swarms on this server.
- `swarm-get`: Get a specific MAIL swarm by name on this server.

### Mailing List Helpers

- `lists`: Get the mailing lists on this MAIL server for the authorized user-agent.
- `list-get`: Get a specific mailing list on this MAIL server by address.
- `list-subscribe`: Subscribe to an existing mailing list by address on this MAIL server.
- `list-unsubscribe`: Unsubscribe from an existing mailing list by address on this MAIL server.

### Utility Commands

- `ping`: Attempt to ping the MAIL server at the URL provided.
- `login`: Log into a MAIL server with valid credentials to obtain a temporary access token.
- `whoami`: View information on the logged-in MAIL user-agent.

## Top-level Options

- `-o`/`--output`: Choose the style of console output for this command.
  - **Default**: `text`
  - **Choices**: `text`, `json`

## Examples

Draft and send a message with tags:

```bash
mail compose "Status update" "All systems nominal." --tags weekly status
mail send <draft_id> sage@chorus@localhost --tags urgent
```

Reply to a message in your inbox (replies to the original sender, subject
defaults to `Re: <original subject>`):

```bash
mail reply <message_id> "Thanks, acknowledged."
mail reply <message_id> "See attached." --subject "Follow-up" --tags project-x
```

Forward a message from your inbox to new recipient(s) (the original message is
encoded into the forwarded body, subject defaults to `Fwd: <original subject>`):

```bash
mail forward <message_id> sage@chorus@localhost
mail forward <message_id> sage@chorus@localhost philosopher@chorus@localhost \
  --note "Please take a look." --subject "Heads up" --tags fyi
```
