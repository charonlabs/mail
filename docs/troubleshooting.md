# Troubleshooting

This document contains various tips on how to ensure your MAIL swarm is running correctly.

## Common issues

Below is a list of possible issues you may encounter during setup, and steps you can take to resolve them.

![IMPORTANT]
This list is not exhaustive, and probably never will be. If you run into any resolvable issue worth mentioning, feel free to add it here.

### Server won't start
  - Check required env vars: `AUTH_ENDPOINT`, `TOKEN_INFO_ENDPOINT` (and `LITELLM_PROXY_API_BASE` only if your swarm uses `use_proxy=true`)
  - Verify `mail.toml` (or `MAIL_CONFIG_PATH`) points at the correct swarm source and registry file
  - Verify **Python 3.12+** and dependency install
  
### Auth errors
  - Ensure the auth endpoints respond and the token has the correct role
  - The server expects `Authorization: Bearer <token>` for nearly all endpoints
  
### No response from agents
  - Confirm [swarms.json](/swarms.json) factory and prompt import paths are valid
  - Ensure at least one supervisor agent exists and is the configured entrypoint
  
### Interswarm routing fails
  - Use `agent@swarm` addressing and register swarms via `/swarms`
  - Verify swarm name/registry settings in `mail.toml`, the registry persistence file path, and env var tokens (set `SWARM_AUTH_TOKEN_<SWARM>` before startup)
  
### SSE stream disconnects
  - Check client and proxy timeouts; events include periodic ping heartbeats

## Logs
- **Enable logging** to debug flow and events
- See [src/mail/utils/logger.py](/src/mail/utils/logger.py) for initialization

## Where to ask
- **Open an issue** with endpoint responses, logs, and your `swarms.json` (redact secrets)
