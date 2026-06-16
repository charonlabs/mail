# Delivery Model

Status: stub

## Question

Why does MAIL store sent messages first and rely on daemons for delivery?

## Source Material

- `spec/SPEC.md` section 8
- `src/mail/daemon/src/mail_daemon/maild/api.py`
- `src/mail/server/src/mail_server/routers/daemon.py`
- `src/mail/server/src/mail_server/backends/base.py`
- `tests/integration/test_flows.py`

## Topics to Discuss

- Draft creation versus sent message creation.
- Server delivery buffer.
- Daemon authorization and delivery responsibility.
- Local delivery versus future remote delivery concerns.
- Pre-send validation failures versus post-send delivery failures.
- Operational implications for retries, observability, and idempotency.

## Related Pages

- [Run the MAIL Daemon](../howtos/run-daemon.md)
- [Daemon CLI](../references/daemon-cli.md)
- [HTTP API](../references/http-api.md)
