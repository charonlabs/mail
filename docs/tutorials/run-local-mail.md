# Run MAIL Locally

Status: draft

## Outcome

The reader starts a local MAIL v2 deployment with the memory backend, logs in as
at least two user-agents, runs a daemon, sends one message, and verifies that
the message was delivered.

## Audience

New contributors and first-time users who have cloned the repository and want a
working local loop before reading deeper docs.

<<<<<<< HEAD
## Not Here

- Exhaustive command flags belong in reference pages.
- Deployment hardening belongs in how-to guides and explanations.

## Steps

### 1. Install workspace dependencies

With the `mail` repository downloaded, navigate into it and use `uv` to install workspace dependencies:

```bash
cd mail
uv sync
```

### 2. Configure the server environment

The MAIL server expects a number of environment variables to be set in order to run.
These are:
- `MAIL_HOST`: The host domain or IP address for this MAIL server. Use `localhost` for this tutorial.
- `MAIL_JWT_SECRET_KEY`: The secret key for the MAIL server to use for JWT auth. Run `openssl rand -hex 32` and use that value for this tutorial.
- `MAIL_JWT_ALGORITHM`: The JWT algorithm used by the MAIL server. Use `HS256` for this tutorial.
- `MAIL_JWT_EXPIRE_MINUTES`: The lifetime to use for JWTs on this MAIL server. Use `30` for this tutorial.

### 3. Initialize the memory backend

The MAIL server uses an in-memory backend by default that saves data to the local filesystem.
This backend must be initialized prior to running `mail-server`.
To initialize the memory backend, run:

```bash
uv run backend-init --type memory --host localhost
```

This script will set up a new MAIL memory backend deployment in the local filesystem.
It will also generate credentials for one user-agent of each type: `agent`, `admin`, `daemon`, and `user`.
For each user-agent, the password will be written to the filepath printed to the console.
Copy these credentials into a safe place and then delete the files.

### 4. Start `mail-server`

With your environment configured as described in step 2, you can now start up the MAIL server:

```bash
uv run mail-server --backend memory
```

The MAIL server (hosted on `http://127.0.0.1:8865`) will start up using the memory backend you just initialized.

### 5. Log in as a sender and recipient

Once the MAIL server is up and running, open a new terminal and log in as the `admin` user-agent that was just created:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_ADDRESS=admin:dummy@localhost
MAIL_PASSWORD={admin_password}
uv run mail login
```

Use the `admin` password that was generated in step 3. We'll use this user-agent to send a MAIL message. Running `login` should print a generated JWT for this admin that can be used in subsequent operations.

Then, open another terminal and log in as the `agent` user-agent that was just created:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_ADDRESS=supervisor@default@localhost
MAIL_PASSWORD={agent_password}
uv run mail login
```

Use the `agent` password that was generated in step 3. We'll use this user-agent to receive the MAIL message sent by the `admin`. Running `login` should print a generated JWT for this agent that can be used in subsequent operations.

### 6. Start `mail-daemon` with daemon credentials

In order for MAIL messages to be delivered between user-agents, an authenticated daemon must be connected to the server.
Open another terminal and run `mail-daemon` with the generated credentials from step 3:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_ADDRESS=daemon:dummy@localhost
MAIL_PASSWORD={daemon_password}
uv run mail-daemon
```

The MAIL daemon should then start up and log in to the server. When there are new messages on the server to deliver, the daemon will deliver them to the specified recipient(s).

### 7. Compose and send a message

We will now attempt to compose and send a message as the `admin` that was authenticated in step 5. To compose a new message draft as `admin:dummy@localhost`, run:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_TOKEN={admin_jwt}
uv run mail compose "Test subject" "This is a message body"
```

You should see the new draft printed to the console, including its unique draft ID (a UUID). We can now send a MAIL message to the `agent` by specifying the draft ID and the agent's address:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_TOKEN={admin_jwt}
uv run mail send {draft_id} supervisor@default@localhost
```

You should see a MAIL message created from the draft that you just composed, including its unique message ID (a UUID). This will be delivered by the daemon (from step 6) to `supervisor@default@localhost`. Note that this process may take up to 30 seconds.

### 8. Open inbox and outbox entries to confirm delivery

To check that the `admin`'s message has been delivered, open the `agent`'s inbox using their JWT from step 5:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_TOKEN={agent_jwt}
uv run mail inbox
```

Once the message has been delivered, you should see it in the `agent` inbox. Open and read the full message:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_TOKEN={agent_jwt}
uv run mail open {message_id}
```

You should now see the message composed by the `admin` with the subject "Test subject" and body "This is a message body". At the bottom of the message, you should also see:

```text
Delivered By: daemon:dummy@localhost
```

You can also access this message in the sending `admin`'s outbox. To do so, use the `admin`'s JWT from step 5:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_TOKEN={admin_jwt}
uv run mail outbox
```

Assuming the composed message ID is present, you can open and read it with:

```bash
MAIL_SERVER=http://127.0.0.1:8865
MAIL_TOKEN={admin_jwt}
uv run mail outbox-open {message_id}
```

Like in the `agent`'s inbox, you should see the message contents as you composed them, with a subject of "Test subject" and a body of "This is a message body".

=======
>>>>>>> 4bed686 (docs: rebased v2 docs branch with main)
## Source Material

- `README.md`
- `src/mail/server/docs/tutorials/quickstart.md`
- `src/mail/client/docs/tutorials/quickstart.md`
- `src/mail/server/.env.example`
- `src/mail/server/src/mail_server/backend_init.py`
- `src/mail/daemon/src/mail_daemon/maild/api.py`
<<<<<<< HEAD
=======

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
>>>>>>> 4bed686 (docs: rebased v2 docs branch with main)
