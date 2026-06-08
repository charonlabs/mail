# `mail-client` Admin Panel CLI Reference

This document serves as a reference to the `mail-client` administrator panel CLI.

## Usage

```bash
mail-admin [option]... <command> [argument]...
```

## Commands

### Agent Operations

- `agent-list`: Get a list of agents registered on the MAIL server.
- `agent-get`: Get a specific agent by local address (agent@swarm) on the MAIL server.
- `agent-post`: Create a new agent with the specified credentials on the MAIL server.
- `agent-delete`: Delete an existing agent by local address (agent@swarm) on the MAIL server.

### Daemon Operations

- `daemon-list`: Get a list of daemons registered on the MAIL server.
- `daemon-get`: Get a specific daemon by worker name on the MAIL server.
- `daemon-post`: Create a new daemon with the specified credentials on the MAIL server.
- `daemon-delete`: Delete an existing daemon by worker name on the MAIL server.

### User Operations

- `user-list`: Get a list of users registered on the MAIL server.
- `user-get`: Get a specific user by ID on the MAIL server.
- `user-post`: Create a new user with the specified credentials on the MAIL server.
- `user-delete`: Delete an existing user by ID on the MAIL server.

### Swarm Operations

- `swarm-post`: Create a new swarm with the specified info on the MAIL server.
- `swarm-delete` Delete an existing swarm by name on the MAIL server.

### Webhook Operations

- `webhook-list`: Get a list of webhooks registered on the MAIL server.
- `webhook-get`: Get a specific webhook by ID on the MAIL server.
- `webhook-post`: Cerate a new webhook on the MAIL server.
- `webhook-patch`: Update an existing webhook by ID on the MAIL server.
- `webhook-delete`: Delete an existing webhook by ID on the MAIL server.

### Mailing List Operations

- `list-list`: Get all mailing lists on the MAIL server.
- `list-get`: Get a specific mailing list by address on the MAIL server.
- `list-post`: Create a new mailing list on the MAIL server.
- `list-patch` Update an existing mailing list on the MAIL server.
- `list-delete`: Delete an existing mailing list by address from the MAIL server.
- `list-member-post`: Add a new member to the existing mailing list on the MAIL server.
- `list-member-delete`: Remove a member from an existing mailing list on the MAIL server.

### Utility Commands (same as main CLI)

- `ping`: Attempt to ping the MAIL server at the URL provided.
- `login`: Log into a MAIL server with valid credentials to obtain a temporary access token.
- `whoami`: View information on the logged-in MAIL user-agent.

## Top-level Options

- `-o`/`--output`: Choose the style of console output for this command.
  - **Default**: `text`
  - **Choices**: `text`, `json`
