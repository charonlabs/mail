# Security Model

Status: draft

MAIL's security model follows from one fact: the **server is the sole authority**.
It owns all state, authenticates every user-agent, and enforces what each may do.
Clients and daemons hold no authority of their own — they act only with a valid
token. This page explains the trust boundaries and operational expectations; the
normative security clauses are SPEC §9, and the implementation is in
[`auth.py`](../../src/mail/server/src/mail_server/auth.py) and
[`routers/auth.py`](../../src/mail/server/src/mail_server/routers/auth.py).

## Authentication: passwords to tokens

A user-agent exchanges its address and password for a short-lived **access
token** (a JWT) via `POST /auth/token`. Every subsequent request carries it as
`Authorization: Bearer <token>`, and the server verifies the signature and expiry
on each call. Token lifetime is set by `MAIL_JWT_EXPIRE_MINUTES`; the signing key
and algorithm by `MAIL_JWT_SECRET_KEY` / `MAIL_JWT_ALGORITHM` (see
[Configuration](../references/configuration.md)). See
[Authenticate a User-Agent](../howtos/authenticate-user-agent.md).

### Refresh tokens

Because access tokens are short-lived, **interactive principals** — users and
admins — also receive a **refresh token** at login, which renews an access token
without re-entering the password. Agents and daemons are *not* interactive
principals: they re-authenticate with their credentials instead. The design:

- **Rotation.** Each `POST /auth/refresh` invalidates the presented token and
  issues a replacement. Tokens are grouped into a *family* with a single absolute
  expiry carried forward across rotations.
- **Reuse detection.** Presenting an already-rotated token is treated as
  compromise and revokes the whole family; a password reset revokes all families.
- **Transport.** For browsers the refresh token is an `httpOnly`,
  `SameSite=strict` cookie scoped to `/auth` (so it is never sent to the wider
  API), with the `Secure` flag on by default (`MAIL_COOKIE_SECURE`). CLI clients,
  which cannot use the cookie, send it in the request body.

## Trust boundaries by role

- **Admins** are the most powerful principals: they create and delete agents,
  users, daemons, swarms, lists, and webhooks. Admin credentials are effectively
  server-control credentials — generate and hand them out with extreme caution
  (SPEC §5.1).
- **Daemons** are trusted couriers. They deliver messages but MUST NOT read,
  alter, or compose message content, and SHOULD NOT send messages of their own
  (SPEC §5.3). A compromised daemon is a delivery-integrity problem, so treat its
  credentials with the same caution as admin credentials.
- **Agents and users** may compose and send messages, manage their own list
  subscriptions, and read limited server metadata — nothing administrative.

## Secret handling

- **Credentials via environment, not arguments.** Clients and daemons read
  `MAIL_PASSWORD` / tokens from environment variables rather than command-line
  flags, keeping secrets out of shell history (SPEC §9.1–9.2). The CLI never
  writes tokens to disk — it prints them for you to export.
- **Don't log sensitive data.** Message contents and credentials SHOULD NOT be
  logged by clients, daemons, or the server (SPEC §9).
- **Plaintext init secrets.** `backend-init` writes generated passwords in
  plaintext under `.secrets/`; capture and delete them promptly (see
  [Initialize the Memory Backend](../howtos/initialize-memory-backend.md)).

## Production expectations (SPEC §9.3)

- Serve over **TLS**; keep `MAIL_COOKIE_SECURE` on so refresh cookies are
  HTTPS-only.
- Put the server **behind a reverse proxy** for load balancing and rate limiting.
- Rotate user-agent passwords periodically (SPEC §9.4).

## Related pages

- [Authenticate a User-Agent](../howtos/authenticate-user-agent.md)
- [Configuration](../references/configuration.md)
- [Protocol Specification](../references/protocol-specification.md)
