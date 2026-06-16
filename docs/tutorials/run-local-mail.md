# Run MAIL Locally

Status: stub

## Outcome

The reader starts a local MAIL v2 deployment with the memory backend, logs in as
at least two user-agents, runs a daemon, sends one message, and verifies that
the message was delivered.

## Audience

New contributors and first-time users who have cloned the repository and want a
working local loop before reading deeper docs.

## Source Material

- `README.md`
- `src/mail/server/docs/tutorials/quickstart.md`
- `src/mail/client/docs/tutorials/quickstart.md`
- `src/mail/server/.env.example`
- `src/mail/server/src/mail_server/backend_init.py`
- `src/mail/daemon/src/mail_daemon/maild/api.py`

## Draft Outline

1. Install workspace dependencies with `uv sync`.
2. Configure the server environment.
3. Initialize the memory backend with `backend-init`.
4. Start `mail-server`.
5. Log in as a sender and recipient with `mail login`.
6. Start `mail-daemon` with daemon credentials.
7. Compose and send a message.
8. Open inbox and outbox entries to confirm delivery.

## Not Here

- Exhaustive command flags belong in reference pages.
- Deployment hardening belongs in how-to guides and explanations.
