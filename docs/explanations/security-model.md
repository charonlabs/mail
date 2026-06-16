# Security Model

Status: stub

## Question

What are MAIL trust boundaries, credential risks, and minimum operational
expectations?

## Source Material

- `spec/SPEC.md` section 9
- `src/mail/server/src/mail_server/auth.py`
- `src/mail/server/src/mail_server/routers/auth.py`
- `src/mail/server/.env.example`
- `tests/integration/test_auth.py`
- `tests/integration/test_authz.py`

## Topics to Discuss

- User-agent credentials and bearer tokens.
- Admin power and account creation risks.
- Daemon privileges.
- Secret handling in CLI and environment variables.
- TLS and reverse proxy expectations for production.
- Logging risks for message content and credentials.

## Related Pages

- [Authenticate a User-Agent](../howtos/authenticate-user-agent.md)
- [Configuration](../references/configuration.md)
- [Protocol Specification](../references/protocol-specification.md)
