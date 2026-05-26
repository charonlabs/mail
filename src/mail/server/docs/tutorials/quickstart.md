# `mail-server` Quickstart

This document serves as a tutorial on how to get started with `mail-server`.

## Prerequesites

- `mail` GitHub repository cloned OR `mail-swarms` installed from PyPI
- `mail` CLI client installed from either of the above

## Required Environment Variables

`mail-server` uses a number of environment variables to allow for easy deployment configuration.

The following environment variables are required for `mail-server` to run:
- `MAIL_JWT_ALGORITHM`: The JWT algorithm for this MAIL server to use.
  - **Example**: `HS256`
- `MAIL_JWT_SECRET_KEY`: The secret key to use for the JWT process on the MAIL server.
  - **Example**: `0d67b4cce591d1ff298fdbc8781f721b811d0483d9892c66dd7f430d15c42492`
- `MAIL_JWT_EXPIRE_MINUTES`: The lifetime in minutes of JWTs issues by the MAIL server.
  - **Example**: `30`

> [!NOTE]
> Refer to `.env.example` in the `mail-server` root for an example environment variable configuration to test with.

## `memory` Backend Setup

Before you can run `mail-server`, you need to initialize a backend.
To initialize the basic `memory` backend, run:

```bash
uv run backend-init
```

By default, this process creates a fresh `memory` backend with the following:
- A server deployment container `default`
- A MAIL swarm named `default`
- A local agent `supervisor@default@example.com`
- A local daemon `daemon:dummy@example.com`
- A local user `user:dummy@example.com`
- A local administrator `admin:dummy@example.com`

> [!NOTE]
> You can configure the backend initialization process if desired.
> Run `uv run backend-init --help` for options.

All four user-agents listed above have associated plain-text password stored in the paths printed.

> [!CAUTION]
> Copy the generated passwords and keep them in a safe place.
> Afterwards, remove the files generated from the backend filesystem.

## Running the Server

With your environment variables configured, try running `mail-server`:

```bash
uv run mail-server 
```

The server should start up successfully on `http://127.0.0.1:8865`. If desired, both the host and port can be configured via options in the `mail-server` CLI.

You can shut down the server by pressing `Ctrl+C`.

## Client Testing

### Agent: `supervisor@default@example.com`

With your server running, open another terminal and run the `mail login` with the required environment variables:

```bash
MAIL_SERVER=http://localhost:8865 \
MAIL_ADDRESS=supervisor@default@example.com \
MAIL_PASSWORD=... \
uv run mail login
```

You should receive a JWT that can be used in subsequent operations.
Test this token by running `mail inbox` with the required environment variables:

```bash
MAIL_SERVER=http://localhost:8865 \
MAIL_TOKEN=... \
uv run mail inbox
```

You should see an empty inbox.

### Daemon: `daemon:dummy@example.com`

With your server running, open another terminal and run the `mail login` with the required environment variables:

```bash
MAIL_SERVER=http://localhost:8865 \
MAIL_ADDRESS=daemon:dummy@example.com \
MAIL_PASSWORD=... \
uv run mail login
```

You should receive a JWT that can be used in subsequent operations.
Test this token by running `mail inbox` with the required environment variables:

```bash
MAIL_SERVER=http://localhost:8865 \
MAIL_TOKEN=... \
uv run mail inbox
```

You should see an empty inbox.

### User: `user:dummy@example.com`

With your server running, open another terminal and run the `mail login` with the required environment variables:

```bash
MAIL_SERVER=http://localhost:8865 \
MAIL_ADDRESS=user:dummy@example.com \
MAIL_PASSWORD=... \
uv run mail login
```

You should receive a JWT that can be used in subsequent operations.
Test this token by running `mail inbox` with the required environment variables:

```bash
MAIL_SERVER=http://localhost:8865 \
MAIL_TOKEN=... \
uv run mail inbox
```

You should see an empty inbox.

### Admin: `admin:dummy@example.com`

With your server running, open another terminal and run the `mail login` with the required environment variables:

```bash
MAIL_SERVER=http://localhost:8865 \
MAIL_ADDRESS=admin:dummy@example.com \
MAIL_PASSWORD=... \
uv run mail login
```

You should receive a JWT that can be used in subsequent operations.
Test this token by running `mail inbox` with the required environment variables:

```bash
MAIL_SERVER=http://localhost:8865 \
MAIL_TOKEN=... \
uv run mail inbox
```

You should see an empty inbox.
