# `mail-swarms-client` CLI Reference

This document serves as a reference to the `mail-swarms-client` CLI.

## Usage

```bash
mail [option]... <command> [argument]...
```

## Commands

### Core MAIL Operations

- `compose`: Draft a new MAIL message. Accepts `--tags TAG...` to attach slug tags.
- `send`: Send an existing draft by ID to the specified recipient(s). Accepts `--tags TAG...`, which are merged with the draft's tags.
- `reply`: Reply to an existing inbox message by ID. Addresses the reply to the original sender and defaults the subject to `Re: <original subject>`. Accepts `--subject SUBJECT` and `--tags TAG...`.
- `inbox`: Open your MAIL inbox.
- `inbox-open`: Open a specific message by ID in your MAIL inbox.
- `outbox`: Open your MAIL outbox.
- `outbox-open`: Open a specific message by ID in your MAIL outbox.
- `drafts`: List your existing MAIL message drafts.
- `drafts-open`: Open a specific existing draft by ID.
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
