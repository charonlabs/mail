# Initialize the Memory Backend

Status: stub

## Goal

How to create a local memory backend with initial swarms, user-agents, and
credentials for development.

## Starting Point

The repository is cloned, dependencies are installed, and the reader wants local
server state for `mail-server --backend memory`.

## Steps

### 1. Run `backend-init`

You can initialize an in-memory backend for a MAIL server by running the `backend-init` script:

```bash
uv run backend-init
```

By default (i.e., with no specified arguments), this script will generate a new MAIL server backend with the following attributes:
- **Backend Type**: `memory`
- **Deployment**: `default`
- **Swarm Name**: `default`
- **Swarm Description**: `A MAIL swarm`
- **Swarm Keywords**: `[]`
- **Agents**: `['supervisor']`
- **Daemons**: `['dummy']`
- **Users**: `['dummy']`
- **Admins**: `['dummy']`
- **Host**: `example.com`

### 2. Customize deployment, swarm, host, agents, daemons, users, or admins

To initialize a new backend with a different deployment name (e.g. `example`), specify the `-d`/`--deployment` argument for the `backend-init` script:

```bash
uv run backend-init --deployment "example"
```

To initialize a new backend with a different swarm name (e.g. `example`), specify the `-s`/`--swarm` argument:

```bash
uv run backend-init --swarm "example"
```

To initialize a new backend with a different swarm description (e.g. `My custom description`), specify the `-sd`/`--swarm-description` argument:

```bash
uv run backend-init --swarm-description "My custom description"
```

To initialize a new backend with a different list of swarm keywords (e.g. `['dev', 'internal']`), specify the `-sk`/`--swarm-keywords` argument:

```bash
uv run backend-init --swarm-keywords "dev" "internal"
```

To initialize a new backend with a different list of agent names (e.g. `['meta', 'scribe']`), specify the `--agents` argument:

```bash
uv run backend-init --agents "meta" "scribe"
```

For a different list of daemon names (e.g. `['worker-1', 'worker-2']`), specify the `--daemons` argument:

```bash
uv run backend-init --daemons "worker-1" "worker-2"
```

For a different list of user names (e.g. `['user-1', 'user-2', 'user-3']`), specify the `--users` argument:

```bash
uv run backend-init --users "user-1" "user-2" "user-3"
```

For a different list of admin names (e.g. `['a1', 'a2', 'a3', 'a4']`), specify the `--admins` argument:

```bash
uv run backend-init --admins "a1" "a2" "a3" "a4"
```

To initialize a new backend with a different host (e.g. `my-site.com`), specify the `-H`/`--host` argument:

```bash
uv run backend-init --host "my-site.com"
```

### 3. Locate generated credential files

Upon memory backend initialization, a password for each created user-agent is randomly-generated. These passwords will be stored in plaintext inside `~/.mail-swarms/deployments/{deployment}/.secrets`, where `deployment` is the name of the deployment created with `backend-init`.

For example, if you have a deployment named `default` and a user-agent address `supervisor@default@example.com`, you can view its plaintext password:

```bash
cat ~/.mail-swarms/deployments/default/.secrets/supervisor@default@example.com
```

### 4. Remove or protect plaintext password files after capture

Copy the plaintext passwords for the user-agents you intend to keep into a safe place.
Once you have these copied, you can simply delete the `.secrets` folder in your deployment:

```bash
rm -rf ~/.mail-swarms/deployments/{deployment}/.secrets
```

where `deployment` is the name chosen for your deployment.

### 5. Reinitialize clean slate when needed

TODO

## Source Material

- `src/mail/server/src/mail_server/backend_init.py`
- `src/mail/server/src/mail_server/backends/memory/init.py`
- `src/mail/server/docs/tutorials/quickstart.md`
