# Run the MAIL Daemon

Status: draft

## Goal

Start `mail-daemon` so pending messages are delivered from the server into
recipients' inboxes.

## Starting Point

A MAIL server is running and you have daemon credentials — a `daemon:` address
and its password, created by `backend-init` (see
[Initialize the Memory Backend](initialize-memory-backend.md)). Delivery is the
daemon's job, not the server's; see [Delivery Model](../explanations/delivery-model.md).

## Steps

### 1. Set the daemon's environment variables

The daemon authenticates as a daemon user-agent and requires all three:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_ADDRESS=daemon:dummy@localhost
MAIL_PASSWORD={daemon_password}
```

### 2. Start the daemon

```bash
uv run mail-daemon
```

On startup it health-checks the server, logs in to obtain a token, then begins
polling for messages to deliver (roughly every 30 seconds).

### 3. Adjust log levels (optional)

Console and file log levels are set independently (`debug`, `info`, `warning`,
`error`, `critical`; both default to `info`):

```bash
uv run mail-daemon --log-level-console debug --log-level-file info
```

### 4. Confirm delivery

Send a message (see [Send a Message with the CLI](send-message-cli.md)), then
open the recipient's inbox. The message moves from the server's delivery buffer
into the recipient's inbox within one poll cycle, and the delivered message
records `Delivered By: daemon:…`.

## See also

- [Delivery Model](../explanations/delivery-model.md) — why a daemon delivers.
- [Run the MAIL Server](run-server.md)
- [Configuration](../references/configuration.md)

## Source Material

- `src/mail/daemon/src/mail_daemon/cli.py`
- `src/mail/daemon/src/mail_daemon/maild/api.py`
