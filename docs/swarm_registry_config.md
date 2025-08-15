# Swarm Registry Volatility Configuration

This document explains how to configure and use the volatility features in the ACP Swarm Registry.

## Overview

The Swarm Registry now supports **volatile** and **non-volatile** (persistent) swarm endpoints:

- **Volatile endpoints**: Automatically removed when the server shuts down
- **Non-volatile endpoints**: Persisted across server restarts

## Configuration

### Environment Variables

```bash
# Required: Name of the local swarm
export SWARM_NAME="my-swarm"

# Required: Base URL of the local swarm
export BASE_URL="http://localhost:8000"

# Optional: Path to the persistence file (default: swarm_registry.json)
export SWARM_REGISTRY_FILE="/path/to/swarm_registry.json"
```

### Persistence File

The registry automatically creates a JSON file to store persistent endpoints. The default location is `swarm_registry.json` in the current working directory.

## Usage Examples

### 1. Register a Volatile Swarm (Default Behavior)

```python
# This swarm will be removed when the server shuts down
swarm_registry.register_swarm(
    swarm_name="temp-swarm",
    base_url="http://temp-swarm:8000",
    volatile=True  # Default value
)
```

### 2. Register a Persistent Swarm

```python
# This swarm will persist across server restarts
swarm_registry.register_swarm(
    swarm_name="production-swarm",
    base_url="https://prod-swarm.example.com",
    auth_token="secret-token",
    metadata={"environment": "production", "version": "1.0.0"},
    volatile=False  # Make it persistent
)
```

### 3. HTTP API Registration

```bash
# Register a volatile swarm
curl -X POST http://localhost:8000/swarms/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "temp-swarm",
    "base_url": "http://temp-swarm:8000",
    "volatile": true
  }'

# Register a persistent swarm
curl -X POST http://localhost:8000/swarms/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production-swarm",
    "base_url": "https://prod-swarm.example.com",
    "auth_token": "secret-token",
    "metadata": {"environment": "production"},
    "volatile": false
  }'
```

## How It Works

### Server Startup
1. The registry loads persistent endpoints from the persistence file
2. Health checks are started for all endpoints
3. The registry is ready for interswarm communication

### Server Shutdown
1. Health checks are stopped
2. All volatile endpoints are removed from memory
3. Persistent endpoints are saved to the persistence file
4. The server shuts down cleanly

### Server Restart
1. The registry is recreated
2. Persistent endpoints are loaded from the persistence file
3. Health checks are restarted
4. The registry resumes normal operation

## Best Practices

### When to Use Volatile Endpoints
- Temporary development/testing swarms
- Swarms that may not be available on restart
- Dynamic discovery scenarios
- Load balancer endpoints

### When to Use Persistent Endpoints
- Production swarms with stable URLs
- Swarms that should always be available
- Long-term interswarm relationships
- Swarms with authentication tokens

### Security Considerations
- Authentication tokens are stored in plain text in the persistence file
- Ensure the persistence file has appropriate file permissions
- Consider encrypting sensitive metadata
- Regularly rotate authentication tokens

## Monitoring and Debugging

### Check Registry Status

```bash
# Get all registered endpoints
curl http://localhost:8000/status

# Check the persistence file
cat swarm_registry.json
```

### Log Messages

The registry logs important events:
- Endpoint registration/unregistration
- Persistence file operations
- Health check results
- Cleanup operations

### Troubleshooting

1. **Endpoints not persisting**: Check file permissions and disk space
2. **Volatile endpoints still present**: Verify the `volatile` parameter is set correctly
3. **Persistence file corruption**: Delete the file and restart (endpoints will be lost)
4. **Health check failures**: Check network connectivity and swarm availability

## Example Configuration Files

### Minimal Configuration
```json
{
  "local_swarm_name": "my-swarm",
  "local_base_url": "http://localhost:8000",
  "endpoints": {}
}
```

### With Persistent Endpoints
```json
{
  "local_swarm_name": "my-swarm",
  "local_base_url": "http://localhost:8000",
  "endpoints": {
    "production-swarm": {
      "swarm_name": "production-swarm",
      "base_url": "https://prod-swarm.example.com",
      "health_check_url": "https://prod-swarm.example.com/health",
      "auth_token": "secret-token",
      "last_seen": "2024-01-01T12:00:00",
      "is_active": true,
      "metadata": {"environment": "production"},
      "volatile": false
    }
  }
}
``` 