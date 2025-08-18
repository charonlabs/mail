# Authentication Token Reference Implementation

This document explains how the new `auth_token_ref` functionality works in the ACP Swarm Registry.

## Overview

When you register a **persistent swarm** (with `volatile=False`), the registry automatically converts authentication tokens to environment variable references instead of storing them in plain text. This provides enhanced security by ensuring sensitive tokens are never persisted in configuration files.

## How It Works

### 1. Automatic Conversion

When you register a persistent swarm:

```python
swarm_registry.register_swarm(
    swarm_name="production",
    base_url="https://prod.example.com",
    auth_token="secret-token-12345",  # This will be converted
    volatile=False  # This triggers the conversion
)
```

The registry automatically:
- Detects that this is a persistent swarm (`volatile=False`)
- Converts the `auth_token` to an environment variable reference
- Stores it in the `auth_token_ref` field
- Generates a unique environment variable name

### 2. Environment Variable Naming

The registry generates environment variable names using this pattern:
```
SWARM_AUTH_TOKEN_{LOCAL_SWARM_NAME_UPPERCASE}
```

For example, if your local swarm is named `swarm-alpha`, the environment variable would be:
```
SWARM_AUTH_TOKEN_SWARM_ALPHA
```

### 3. Storage Format

**Before (old behavior):**
```json
{
  "auth_token": "secret-token-12345"
}
```

**After (new behavior):**
```json
{
  "auth_token_ref": "${SWARM_AUTH_TOKEN_SWARM_ALPHA}"
}
```

## Usage Examples

### Registering a Persistent Swarm

```python
from acp.swarm_registry import SwarmRegistry

# Create registry
registry = SwarmRegistry("my-swarm", "http://localhost:8000")

# Register persistent swarm - token automatically converted to env var reference
registry.register_swarm(
    swarm_name="production",
    base_url="https://prod.example.com",
    auth_token="your-secret-token",
    volatile=False
)

# The token is now stored as: ${SWARM_AUTH_TOKEN_MY_SWARM}
```

### Setting Environment Variables

```bash
# Set the environment variable with your actual token
export SWARM_AUTH_TOKEN_MY_SWARM="your-secret-token"

# Or in your .env file
echo "SWARM_AUTH_TOKEN_MY_SWARM=your-secret-token" >> .env
```

### Retrieving the Resolved Token

```python
# Get the resolved (actual) token value
actual_token = registry.get_resolved_auth_token("production")

# This will return the value of the environment variable
# or None if the environment variable is not set
```

## Volatile vs Persistent Swarms

### Volatile Swarms (`volatile=True`)
- Store `auth_token` as-is in `auth_token_ref`
- No automatic conversion
- Tokens are stored in plain text (but removed on server shutdown)

### Persistent Swarms (`volatile=False`)
- Automatically convert `auth_token` to environment variable reference
- Store reference in `auth_token_ref`
- Tokens are never stored in plain text in persistence files

## Migration from Existing Registries

If you have existing registries with plain text tokens, you can migrate them:

```python
# Migrate all existing tokens to environment variable references
registry.migrate_auth_tokens_to_env_refs()

# Or use a custom prefix
registry.migrate_auth_tokens_to_env_refs("CUSTOM_PREFIX")
```

## Security Benefits

1. **No Plain Text Tokens**: Authentication tokens are never stored in plain text in persistence files
2. **Environment-Specific**: Different environments can use different tokens without code changes
3. **Easy Rotation**: Update environment variables to rotate tokens without modifying registry files
4. **CI/CD Friendly**: Perfect for automated deployments where tokens are injected as environment variables

## Best Practices

1. **Set Environment Variables**: Always set the required environment variables before starting your application
2. **Use Secrets Management**: Store tokens in secure vaults (HashiCorp Vault, AWS Secrets Manager, etc.)
3. **Validate Configuration**: Use `validate_environment_variables()` to check that all required variables are set
4. **Monitor Logs**: Watch for warnings about missing environment variables

## Troubleshooting

### Missing Environment Variable Warning

If you see this warning:
```
Environment variable SWARM_AUTH_TOKEN_MY_SWARM for swarm production is not set
```

**Solution**: Set the environment variable:
```bash
export SWARM_AUTH_TOKEN_MY_SWARM="your-actual-token"
```

### Token Resolution Returns None

If `get_resolved_auth_token()` returns `None`:

1. Check that the environment variable is set
2. Verify the environment variable name matches exactly
3. Ensure the variable is accessible to your application process

### Backward Compatibility

The implementation maintains backward compatibility:
- Old registries with `auth_token` fields continue to work
- New registries use `auth_token_ref` fields
- The `get_resolved_auth_token()` method handles both formats

## API Reference

### New Methods

- `get_resolved_auth_token(swarm_name: str) -> Optional[str]`: Get the resolved authentication token for a swarm
- `_get_auth_token_ref(auth_token: Optional[str]) -> Optional[str]`: Convert auth token to environment variable reference
- `_resolve_auth_token_ref(auth_token_ref: Optional[str]) -> Optional[str]`: Resolve environment variable reference to actual token

### Updated Fields

- `SwarmEndpoint.auth_token_ref`: Now stores environment variable references instead of plain text tokens
- `SwarmEndpoint.auth_token`: Removed (replaced by `auth_token_ref`)

## Example Complete Workflow

```python
# 1. Set environment variable
import os
os.environ["SWARM_AUTH_TOKEN_MY_SWARM"] = "secret-token-12345"

# 2. Create registry
registry = SwarmRegistry("my-swarm", "http://localhost:8000")

# 3. Register persistent swarm
registry.register_swarm(
    swarm_name="production",
    base_url="https://prod.example.com",
    auth_token="secret-token-12345",
    volatile=False
)

# 4. Verify conversion
endpoint = registry.get_swarm_endpoint("production")
print(f"Stored reference: {endpoint['auth_token_ref']}")
# Output: ${SWARM_AUTH_TOKEN_MY_SWARM}

# 5. Get resolved token
actual_token = registry.get_resolved_auth_token("production")
print(f"Resolved token: {actual_token}")
# Output: secret-token-12345

# 6. Use in HTTP requests
import aiohttp
headers = {}
if actual_token:
    headers["Authorization"] = f"Bearer {actual_token}"
```

This implementation ensures that your authentication tokens are secure while maintaining the flexibility and persistence of your swarm registry configuration.
