# Swarm Registry

The registry manages discovery and routing for remote swarms.

## Responsibilities
- **Track endpoints**: name, base URL, health URL, auth token reference
- Periodic **health checks** and last-seen timestamps
- **Persistence** of non-volatile entries to a JSON file
- Migration and validation of env-backed auth tokens

## Persistence
- **File**: registry path from `mail.toml` (`[server.swarm].registry` / `registry_file`), default `registries/example-no-proxy.json`
- On shutdown, volatile entries are discarded; persistent entries are saved

## Auth token references
- Persistent registrations convert `auth_token` to environment references like `${SWARM_AUTH_TOKEN_<SWARM>}`
- At runtime these are resolved from the process environment; if unset the router will fall back to the message payload’s `auth_token`, but you should still export the variable so outbound calls always include a static bearer token.
- **Utilities**: `migrate_auth_tokens_to_env_refs`, `validate_environment_variables`

## API integration
- **Server endpoints** expose `GET /swarms`, `POST /swarms`, `GET /swarms/dump`, `POST /swarms/load`
- Use `POST /swarms` with `volatile=false` to persist a remote swarm

## Code
- [src/mail/net/registry.py](/src/mail/net/registry.py)
- [src/mail/net/router.py](/src/mail/net/router.py)
