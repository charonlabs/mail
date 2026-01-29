# Security

## Recommendations
- **Use HTTPS** for all deployments and registry communications
- **Separate tokens** and roles for users, admins, and agents
- Require admin role for registry mutations and loading swarms
- Use environment variable references for persistent interswarm auth tokens
- Apply rate limiting at HTTP ingress if public facing
- **Restrict tool execution**; validate parameters and avoid dangerous side effects

## Auth integration
- The server delegates token validation to `TOKEN_INFO_ENDPOINT`
- **Expected shape**: `{ role: "admin"|"user"|"agent", id: string, api_key: string }`
- Per-user MAIL instances are keyed by caller role + id; task owner identifiers use `{role}:{id}@{swarm}`

## Operational
- Keep `SWARM_REGISTRY_FILE` on secure storage and ensure only env-var references are persisted
- **Rotate environment variables** instead of editing persisted JSON
- **Monitor logs** for interswarm health changes and failures
