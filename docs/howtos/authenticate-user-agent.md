# Authenticate a User-Agent

Status: draft

## Goal

How to exchange MAIL address credentials for a bearer token and use that token
with CLI or HTTP requests.

## Starting Point

The reader has a server URL, a MAIL address, and a password.

## Steps

### 1. Set environment variables

In order to log into a MAIL server using the MAIL client CLI, you must set the following environment variables:
- `MAIL_SERVER`: The URL of the MAIL server to log into, e.g. `https://mail-swarms.example.com`.
- `MAIL_ADDRESS`: The address of the MAIL user-agent to log in as, e.g. `user:example@example.com`.
- `MAIL_PASSWORD`: The password for the MAIL user-agent to log in as.

### 2. Run `mail login`

With the environment variables set as described in step 1, log into the MAIL server using the CLI client command `login`:

```bash
uv run mail login
```

### 3. Store the returned token in `MAIL_TOKEN`

Running the `login` command above should print a temporary access token to the console.
This can be used in subsequent operations with the `mail` client CLI, rather than `MAIL_ADDRESS` and `MAIL_PASSWORD`.
Store this token as an environment variable called `MAIL_TOKEN`:

```env
MAIL_TOKEN={token}
```

If you logged in as a **user** or **admin** (an *interactive principal*), `login` also prints a **refresh token**. Store it as `MAIL_REFRESH_TOKEN` so you can renew your access token later without re-entering your password (see step 6). Agents and daemons are not issued refresh tokens and re-authenticate with their credentials instead.

### 4. Run `mail whoami`

With your `MAIL_SERVER` and `MAIL_TOKEN` environment variables set, you can now view your own user-agent information using the `whoami` command:

```bash
uv run mail whoami
```

This will print the authenticated user-agent's MAIL address and user-agent type. Ensure these are both the expected values.

### 5. Use the token in an HTTP `Authorization: Bearer ...` header

Since the MAIL server accepts access tokens in the `Authorization` header, you can attempt to hit the `whoami` endpoint with a raw HTTP request rather than through the `mail` client CLI:

```bash
curl {server_url}/auth/whoami \
-H "Authorization: Bearer {token}"
```

### 6. Refresh or replace expired tokens

Server-issued access tokens will expire after a predetermined length of time (e.g. 15, 30, or 60 minutes). If you attempt to hit a MAIL server endpoint with a previously-valid token and get a `401` response, that likely means your token has expired.

If you saved a refresh token in step 3 (users and admins only), renew your access token without re-entering credentials by running `mail refresh` with `MAIL_SERVER` and `MAIL_REFRESH_TOKEN` set:

```bash
MAIL_SERVER={server_url}
MAIL_REFRESH_TOKEN={refresh_token}
uv run mail refresh
```

Refresh tokens are **rotated**: each `mail refresh` invalidates the token you sent and prints a replacement, so update `MAIL_REFRESH_TOKEN` with the new value every time. Store the new access token in `MAIL_TOKEN` as in step 3.

Agents and daemons are not issued refresh tokens; they obtain a fresh access token by logging in again (repeat steps 1-2).

## Source Material

- `src/mail/client/src/mail_client/commands/login.py`
- `src/mail/client/src/mail_client/commands/whoami.py`
- `src/mail/server/src/mail_server/routers/auth.py`
- `spec/openapi.yaml`
