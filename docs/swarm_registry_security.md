# Swarm Registry Security Configuration

This document explains how to securely configure the MAIL Swarm Registry using environment variables for authentication tokens.

## Security Overview

The Swarm Registry now supports storing authentication tokens as environment variable references instead of plain text in the persistence file. This provides several security benefits:

- **No plain text tokens** in configuration files
- **Environment-specific** token management
- **Easy rotation** of tokens without file changes
- **CI/CD friendly** for automated deployments

## Environment Variable References

### Format
Authentication tokens are stored as environment variable references in the format:
```
${ENVIRONMENT_VARIABLE_NAME}
```

### Example
Instead of storing:
```json
{
  "auth_token": "secret-token-12345"
}
```

The registry stores:
```json
{
  "auth_token_ref": "${SWARM_AUTH_TOKEN_PRODUCTION}"
}
```

## Configuration

### 1. Set Environment Variables

```bash
# For production swarm
export SWARM_AUTH_TOKEN_PRODUCTION="your-actual-production-token"

# For staging swarm  
export SWARM_AUTH_TOKEN_STAGING="your-actual-staging-token"

# For development swarm
export SWARM_AUTH_TOKEN_DEV="your-actual-dev-token"
```

### 2. Register Swarms with References

```python
# The registry will automatically convert tokens to references
swarm_registry.register_swarm(
    swarm_name="production",
    base_url="https://prod.example.com",
    auth_token="your-actual-token",  # This will be converted to ${SWARM_AUTH_TOKEN_PRODUCTION}
    volatile=False
)
```

### 3. Automatic Migration

If you have existing swarms with plain text tokens, you can migrate them:

```python
# Migrate all existing tokens to environment variable references
swarm_registry.migrate_auth_tokens_to_env_refs()

# Or use a custom prefix
swarm_registry.migrate_auth_tokens_to_env_refs("CUSTOM_PREFIX")
```

## Environment Variable Naming Convention

The registry automatically generates environment variable names based on swarm names:

| Swarm Name | Environment Variable | Example Value |
|-------------|---------------------|---------------|
| `production` | `SWARM_AUTH_TOKEN_PRODUCTION` | `prod-secret-123` |
| `staging-1` | `SWARM_AUTH_TOKEN_STAGING_1` | `staging-secret-456` |
| `dev-swarm` | `SWARM_AUTH_TOKEN_DEV_SWARM` | `dev-secret-789` |

## Validation

### Check Environment Variables

```python
# Validate that all required environment variables are set
validation_results = swarm_registry.validate_environment_variables()

for env_var, is_set in validation_results.items():
    if not is_set:
        print(f"Missing environment variable: {env_var}")
```

### Example Output
```
SWARM_AUTH_TOKEN_PRODUCTION: ✅ SET
SWARM_AUTH_TOKEN_STAGING: ❌ NOT SET
```

## Deployment Examples

### Docker Compose

```yaml
version: '3.8'
services:
  mail-server:
    image: your-mail-image
    environment:
      - SWARM_NAME=main-swarm
      - BASE_URL=http://localhost:8000
      - SWARM_AUTH_TOKEN_PRODUCTION=${SWARM_AUTH_TOKEN_PRODUCTION}
      - SWARM_AUTH_TOKEN_STAGING=${SWARM_AUTH_TOKEN_STAGING}
    volumes:
      - ./registries/example.json:/app/registries/example.json
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
  SWARM_AUTH_TOKEN_STAGING: <base64-encoded-token>
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mail-server
spec:
  template:
    spec:
      containers:
      - name: mail-server
        image: your-mail-image
        env:
        - name: SWARM_AUTH_TOKEN_PRODUCTION
          valueFrom:
            secretKeyRef:
              name: swarm-auth-tokens
              key: SWARM_AUTH_TOKEN_PRODUCTION
        - name: SWARM_AUTH_TOKEN_STAGING
          valueFrom:
            secretKeyRef:
              name: swarm-auth-tokens
              key: SWARM_AUTH_TOKEN_STAGING
```

### CI/CD Pipeline

```yaml
# GitHub Actions example
name: Deploy MAIL Server
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    
    - name: Deploy to server
      env:
        SWARM_AUTH_TOKEN_PRODUCTION: ${{ secrets.SWARM_AUTH_TOKEN_PRODUCTION }}
        SWARM_AUTH_TOKEN_STAGING: ${{ secrets.SWARM_AUTH_TOKEN_STAGING }}
      run: |
        # Your deployment script here
        echo "Deploying with secure tokens..."
```

## Security Best Practices

### 1. Token Management
- **Rotate tokens regularly** (e.g., every 90 days)
- **Use strong, random tokens** (32+ characters)
- **Limit token scope** to only necessary permissions

### 2. Environment Security
- **Never commit tokens** to version control
- **Use secrets management** (HashiCorp Vault, AWS Secrets Manager, etc.)
- **Restrict access** to environment variables

### 3. File Permissions
- **Secure the persistence file** with appropriate permissions
- **Consider encryption** for the persistence file in production
- **Regular backups** with secure storage

### 4. Monitoring
- **Log access attempts** to the registry
- **Monitor for missing** environment variables
- **Alert on authentication failures**

## Troubleshooting

### Common Issues

#### 1. Environment Variable Not Found
```
WARNING: Environment variable SWARM_AUTH_TOKEN_PRODUCTION not found for auth token reference
```

**Solution**: Set the environment variable:
```bash
export SWARM_AUTH_TOKEN_PRODUCTION="your-token"
```

#### 2. Token Not Resolving
```
ERROR: Failed to resolve auth token reference ${INVALID_VAR}
```

**Solution**: Check the environment variable name and ensure it's set.

#### 3. Migration Issues
If migration fails, check:
- File permissions on the persistence file
- Available disk space
- Registry state consistency

### Debug Commands

```python
# Check current registry state
print(swarm_registry.get_all_endpoints())

# Validate environment variables
validation_results = swarm_registry.validate_environment_variables()
print(validation_results)

# Check persistence file
with open("registries/example.json", "r") as f:
    print(json.dumps(json.load(f), indent=2))
```

## Migration Guide

### From Plain Text Tokens

1. **Backup your current registry**:
   ```bash
   cp registries/example.json registries/example.json.backup
   ```

2. **Set environment variables** for your tokens:
   ```bash
   export SWARM_AUTH_TOKEN_SWARM1="your-token-1"
   export SWARM_AUTH_TOKEN_SWARM2="your-token-2"
   ```

3. **Migrate the registry**:
   ```python
   swarm_registry.migrate_auth_tokens_to_env_refs()
   ```

4. **Verify the migration**:
   ```python
   # Check that tokens are now references
   for name, endpoint in swarm_registry.get_all_endpoints().items():
       if endpoint.get("auth_token"):
           print(f"{name}: {endpoint['auth_token']}")
   ```

5. **Test the new configuration**:
   ```python
   # Restart the registry to test loading
   new_registry = SwarmRegistry("test", "http://localhost:8000", "registries/example.json")
   ```

## Example Complete Configuration

### Environment Variables
```bash
export SWARM_NAME="main-swarm"
export BASE_URL="https://mail.example.com"
export SWARM_REGISTRY_FILE="/etc/mail/registries/example.json"
export SWARM_AUTH_TOKEN_PRODUCTION="prod-secret-12345"
export SWARM_AUTH_TOKEN_STAGING="staging-secret-67890"
export SWARM_AUTH_TOKEN_DEVELOPMENT="dev-secret-abcde"
```

### Resulting Persistence File
```json
{
  "local_swarm_name": "main-swarm",
  "local_base_url": "https://mail.example.com",
  "endpoints": {
    "production": {
      "swarm_name": "production",
      "base_url": "https://prod.example.com",
      "health_check_url": "https://prod.example.com/health",
      "auth_token_ref": "${SWARM_AUTH_TOKEN_PRODUCTION}",
      "last_seen": "2024-01-01T12:00:00",
      "is_active": true,
      "metadata": {"environment": "production"},
      "volatile": false
    }
  }
}
```

This approach ensures that your authentication tokens are never stored in plain text while maintaining the flexibility and persistence of your swarm registry configuration. 
