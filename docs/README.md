# MAIL Swarm Registry Security Features

This directory contains documentation and tools for securely managing the MAIL Swarm Registry.

## Overview

The MAIL Swarm Registry now supports secure authentication token management using environment variables instead of storing raw tokens in configuration files.

## Key Features

### 🔐 **Secure Token Storage**
- **No plain text tokens** in configuration files
- **Environment variable references** for all sensitive data
- **Automatic migration** from existing plain text tokens

### 🚀 **Easy Deployment**
- **CI/CD friendly** - tokens managed as environment variables
- **Container ready** - works with Docker, Kubernetes, etc.
- **Environment specific** - different tokens for dev/staging/prod

### 🔄 **Automatic Migration**
- **One-command migration** from existing registries
- **Backup creation** before any changes
- **Dry-run mode** to preview changes

## Quick Start

### 1. Set Environment Variables

```bash
# Set your authentication tokens
export SWARM_AUTH_TOKEN_PRODUCTION="your-prod-token"
export SWARM_AUTH_TOKEN_STAGING="your-staging-token"
export SWARM_AUTH_TOKEN_DEVELOPMENT="your-dev-token"
```

### 2. Register Swarms

```python
from mail.swarm_registry import SwarmRegistry

registry = SwarmRegistry("my-swarm", "http://localhost:8000")

# Tokens are automatically converted to environment variable references
registry.register_swarm("production", "https://prod.example.com", 
                       auth_token="your-prod-token", volatile=False)
```

### 3. Migrate Existing Registries

```bash
# Preview migration (dry run)
uv run scripts/migrate_auth_tokens.py swarm_registry.json --dry-run

# Apply migration
uv run scripts/migrate_auth_tokens.py swarm_registry.json
```

## Documentation

- **[Security Configuration](swarm_registry_security.md)** - Complete security setup guide
- **[API Reference](../src/mail/swarm_registry.py)** - Code documentation

## Scripts

- **[Migration Script](../scripts/migrate_auth_tokens.py)** - Convert existing registries
- **[Demo Script](../scripts/demo_persistence.py)** - See features in action
- **[Test Script](../scripts/test_volatility.py)** - Verify functionality

## Examples

### Docker Compose

```yaml
version: '3.8'
services:
  mail-server:
          image: your-mail-image
    environment:
      - SWARM_AUTH_TOKEN_PRODUCTION=${SWARM_AUTH_TOKEN_PRODUCTION}
      - SWARM_AUTH_TOKEN_STAGING=${SWARM_AUTH_TOKEN_STAGING}
```

### Kubernetes

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: swarm-auth-tokens
type: Opaque
data:
  SWARM_AUTH_TOKEN_PRODUCTION: <base64-encoded-token>
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: mail-server
        env:
        - name: SWARM_AUTH_TOKEN_PRODUCTION
          valueFrom:
            secretKeyRef:
              name: swarm-auth-tokens
              key: SWARM_AUTH_TOKEN_PRODUCTION
```

## Security Best Practices

1. **Never commit tokens** to version control
2. **Use secrets management** (Vault, AWS Secrets Manager, etc.)
3. **Rotate tokens regularly** (every 90 days)
4. **Limit token scope** to necessary permissions
5. **Monitor for missing** environment variables

## Getting Help

- Check the [security configuration guide](swarm_registry_security.md)
- Run the demo script: `uv run scripts/demo_persistence.py`
- Use the migration script: `uv run scripts/migrate_auth_tokens.py --help`

## Migration from Plain Text

If you have existing registries with plain text tokens:

1. **Backup your registry**: `cp swarm_registry.json swarm_registry.json.backup`
2. **Set environment variables** for your tokens
3. **Run migration**: `uv run scripts/migrate_auth_tokens.py swarm_registry.json`
4. **Verify**: Check that tokens are now environment variable references

The migration is safe and creates backups automatically. 