# Authenticate a User-Agent

Status: stub

## Goal

How to exchange MAIL address credentials for a bearer token and use that token
with CLI or HTTP requests.

## Starting Point

The reader has a server URL, a MAIL address, and a password.

## Source Material

- `src/mail/client/src/mail_client/commands/login.py`
- `src/mail/client/src/mail_client/commands/whoami.py`
- `src/mail/server/src/mail_server/routers/auth.py`
- `spec/openapi.yaml`

## Steps to Cover

1. Set `MAIL_SERVER`, `MAIL_ADDRESS`, and `MAIL_PASSWORD`.
2. Run `mail login`.
3. Store the returned token in `MAIL_TOKEN`.
4. Run `mail whoami`.
5. Use the token in an HTTP `Authorization: Bearer ...` header.
6. Refresh or replace expired tokens.

## Validation

`mail whoami` returns the expected user-agent type and address.
