# Admin CLI

Status: generated

> **Generated file — do not edit by hand.** Regenerate with `uv run python scripts/build_cli_docs.py` after changing the CLI. See [Regenerate API Artifacts](../howtos/regenerate-api-artifacts.md).

A Python CLI client admin panel for the Multi-Agent Interface Layer (MAIL)

Invoke as `mail-admin` (or `uv run mail-admin` from a workspace checkout). Source: `mail_client/admin_panel.py`.

## Global options

- `--license` — show license information and exit
- `-o`, `--output` `{text,json}` — the output style for this CLI command (default: text)

## Commands

### `ping`  (aliases: `p`)

ping a MAIL server

### `login`  (aliases: `l`)

log into a MAIL server

### `whoami`  (aliases: `me`, `id`)

get authenticated user-agent info from a MAIL server

### `agent-list`  (aliases: `al`)

get a list of agents on the MAIL server

### `agent-get`  (aliases: `ag`)

get a specific agent by local address on the MAIL server

**Arguments:**

- `local_address` — the local address of the agent to get (agent@swarm)

### `agent-post`  (aliases: `ap`)

create a new agent on the MAIL server with the specified credentials

**Arguments:**

- `local_address` — the local address of the agent to create (agent@swarm)

### `agent-delete`  (aliases: `ad`)

delete an existing agent by local address on the MAIL server

**Arguments:**

- `local_address` — the local address of the agent to delete (agent@swarm)

### `daemon-list`  (aliases: `dl`)

get a list of daemons on the MAIL server

### `daemon-get`  (aliases: `dg`)

get a specific daemon by worker name on the MAIL server

**Arguments:**

- `worker_name` — the worker name of the daemon to get

### `daemon-post`  (aliases: `dp`)

create a new daemon on the MAIL server with the specified credentials

**Arguments:**

- `worker_name` — the name to use for the new daemon

### `daemon-delete`  (aliases: `dd`)

delete an existing daemon by worker name on the MAIL server

**Arguments:**

- `worker_name` — the name of the daemon to delete

### `user-list`  (aliases: `ul`)

get a list of users on the MAIL server

### `user-get`  (aliases: `ug`)

get a specific user by user ID on the MAIL server

**Arguments:**

- `user_id` — the ID of the user to get

### `user-post`  (aliases: `up`)

create a new user on the MAIL server with the specified credentials

**Arguments:**

- `user_id` — the ID to use for the new user

### `user-delete`  (aliases: `ud`)

delete an existing user by user ID on the MAIL server

**Arguments:**

- `user_id` — the name of the user to delete

### `swarm-post`  (aliases: `sp`)

create a new swarm on the MAIL server with the specified info

**Arguments:**

- `name` — the name of the swarm to create
- `description` — the description to use for the new swarm

**Options:**

- `-k`, `--keywords` `KEYWORDS` — the keywords to use for this swarm (default: [])

### `swarm-delete`  (aliases: `sd`)

delete an existing swarm by name from the MAIL server

**Arguments:**

- `swarm_name` — the name of the swarm on the server to delete

### `webhook-list`  (aliases: `wl`)

list all webhooks on the MAIL server

### `webhook-get`  (aliases: `wg`)

get an existing webhook by ID on the MAIL server

**Arguments:**

- `webhook_id` — the ID of the webhook to get

### `webhook-post`  (aliases: `wp`)

create a new webhook on the MAIL server

**Arguments:**

- `url` — the URL to hit for this webhook
- `secret` — the secret to use for this webhook

**Options:**

- `-e`, `--events` `EVENTS` — the event(s) for this webhook

### `webhook-patch`  (aliases: `wP`)

update an existing webhook on the MAIL server

**Arguments:**

- `webhook_id` — the ID of the webhook to update

**Options:**

- `-u`, `--url` `URL` — the new URL to use, if any
- `-s`, `--secret` `SECRET` — the new secret to use, if any

### `webhook-delete`  (aliases: `wd`)

delete an existing webhook by ID on the MAIL server

**Arguments:**

- `webhook_id` — the ID of the webhook to delete

### `list-list`  (aliases: `ll`)

get all mailing lists on the MAIL server

### `list-get`  (aliases: `lg`)

get a specific mailing list on the MAIL server by address

**Arguments:**

- `list_address` — the local address of the mailing list to get (name@swarm)

### `list-post`  (aliases: `lp`)

create a new mailing list on the MAIL server

**Arguments:**

- `name` — the name of the new mailing list
- `swarm_name` — the name of the swarm to use for this mailing list
- `owner` — the MAIL address of the mailing list owner

**Options:**

- `-m`, `--members` `MEMBERS` — the MAIL addresses of members to add to this mailing list (default: [])

### `list-patch`  (aliases: `lP`)

update an existing mailing list on the MAIL server

### `list-delete`  (aliases: `ld`)

delete an existing mailing list on the MAIL server by address

**Arguments:**

- `list_address` — the local address of the mailing list to delete (name@swarm)

### `list-member-post`  (aliases: `lmp`)

add a new member to an existing mailing list on the MAIL server

**Arguments:**

- `list_address` — the local address of the mailing list to add a member to (name@swarm)
- `member_address` — the full MAIL address of the member to add to this mailing list

### `list-member-delete`  (aliases: `lmd`)

delete a member from an existing mailing list on the MAIL server

**Arguments:**

- `list_address` — the local address of the mailing list to remove a member from (name@swarm)
- `member_address` — the full MAIL address of the member to remove from this mailing list
