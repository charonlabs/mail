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
- `user-delete`: Delete an existing by ID on the MAIL server.

### Utility Commands (same as main CLI)

- `ping`: Attempt to ping the MAIL server at the URL provided.
- `login`: Log into a MAIL server with valid credentials to obtain a temporary access token.
- `whoami`: View information on the logged-in MAIL user-agent.

## Top-level Options

- `-o`/`--output`: Choose the style of console output for this command.
  - **Default**: `text`
  - **Choices**: `text`, `json`
