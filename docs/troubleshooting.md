# Troubleshooting

This document contains various tips on how to ensure your MAIL swarm is running correctly.

## Common issues

Below is a list of possible issues you may encounter during setup, and steps you can take to resolve them.

![IMPORTANT]
This list is not exhaustive, and probably never will be. If you run into any resolvable issue worth mentioning, feel free to add it here.

### Server won't start
  - Check required env vars: `AUTH_ENDPOINT`, `TOKEN_INFO_ENDPOINT`, `LITELLM_PROXY_API_BASE`, `SWARM_SOURCE`, `SWARM_REGISTRY_FILE`
  - Verify **Python 3.12+** and dependency install
  
### Auth errors
  - Ensure the auth endpoints respond and the token has the correct role
  - The server expects `Authorization: Bearer <token>` for nearly all endpoints
  
### No response from agents
  - Confirm [swarms.json](/swarms.json) factory and prompt import paths are valid
  - Ensure at least one supervisor agent exists and is the configured entrypoint
  
### Interswarm routing fails
  - Use `agent@swarm` addressing and register swarms via `/swarms`
  - Verify `SWARM_NAME`, `BASE_URL`, the registry persistence file, and env var tokens (set them in `mail.toml` or override with environment variables)
  
### SSE stream disconnects
  - Check client and proxy timeouts; events include periodic ping heartbeats

## Logs
- **Enable logging** to debug flow and events
- See [src/mail/utils/logger.py](/src/mail/utils/logger.py) for initialization

## Where to ask
- **Open an issue** with endpoint responses, logs, and your `swarms.json` (redact secrets)
