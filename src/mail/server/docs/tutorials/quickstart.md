# `mail-server` Quickstart

This document serves as a tutorial on how to get started with `mail-server`.

## Prerequesites

- `mail` GitHub repository cloned OR `mail-swarms` installed from PyPI

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

TODO

## Server Dry Run

With your environment variables configured, try running `mail-server`:

```bash
uv run mail-server 
```

The server should start up successfully on `http://127.0.0.1:8865`. If desired, both the host and port can be configured via options in the `mail-server` CLI.

You can shut down the server by pressing `Ctrl+C`.
