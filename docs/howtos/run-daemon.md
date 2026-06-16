# Run the MAIL Daemon

Status: stub

## Goal

How to start `mail-daemon` so pending local messages are delivered by an
authorized daemon user-agent.

## Starting Point

A MAIL server is running and daemon credentials exist.

## Source Material

- `src/mail/daemon/src/mail_daemon/cli.py`
- `src/mail/daemon/src/mail_daemon/maild/api.py`
- `spec/SPEC.md` section 8

## Steps to Cover

1. Set `MAIL_SERVER`, `MAIL_ADDRESS`, and `MAIL_PASSWORD`.
2. Start `uv run mail-daemon`.
3. Adjust console or file log levels.
4. Confirm the daemon obtains a token.
5. Send a message and watch delivery complete.

## Validation

Messages move from the server delivery buffer into recipient inboxes.
