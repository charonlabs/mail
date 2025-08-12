# ACP Interswarm Messaging

This document describes the interswarm messaging feature for ACP (Agent Communication Protocol), which enables communication between agents across different swarms via HTTP.

## Overview

Interswarm messaging allows agents in one swarm to communicate with agents in other swarms using a standardized addressing format and HTTP-based routing. This enables distributed multi-agent systems where different swarms can specialize in different domains while maintaining the ability to collaborate.

## Key Features

- **Interswarm Addressing**: Messages can be sent to agents in other swarms using the format `agent-name@swarm-name`
- **HTTP-based Routing**: Messages are routed between swarms via HTTP(S) requests
- **Service Discovery**: Automatic discovery and registration of swarm endpoints
- **Health Monitoring**: Continuous health checks for swarm availability
- **Authentication**: Support for authentication tokens between swarms
- **Backward Compatibility**: Existing within-swarm messaging continues to work unchanged

## Architecture

### Components

1. **Swarm Registry**: Manages swarm endpoints and service discovery
2. **Interswarm Router**: Handles message routing between swarms
3. **Enhanced Message Types**: Extended ACP messages with swarm routing information
4. **HTTP Endpoints**: REST API endpoints for interswarm communication

### Message Flow

1. Agent A in Swarm Alpha sends message to `agent-b@swarm-beta`
2. Interswarm Router detects interswarm address
3. Router looks up Swarm Beta's endpoint in registry
4. Router sends HTTP POST to Swarm Beta's `/interswarm/message` endpoint
5. Swarm Beta receives message and routes to local Agent B
6. Agent B processes message and can respond back to Swarm Alpha

## Configuration

### Environment Variables

```bash
# Required for interswarm messaging
SWARM_NAME=my-swarm-name
BASE_URL=http://localhost:8000

# Optional: Discovery endpoints
DISCOVERY_URLS=http://registry.example.com/swarms,http://backup-registry.example.com/swarms
```

### Swarm Configuration

Enable interswarm messaging in your swarm configuration:

```json
{
    "name": "my-swarm",
    "agents": [
        {
            "name": "supervisor",
            "comm_targets": ["agent1", "agent2", "external-agent@other-swarm"],
            "agent_params": {
                "enable_interswarm": true
            }
        }
    ]
}
```

## Usage Examples

### Basic Interswarm Communication

```python
# Send message to agent in another swarm
message = ACPMessage(
    id=str(uuid.uuid4()),
    timestamp=datetime.now(),
    message=ACPRequest(
        request_id=str(uuid.uuid4()),
        sender="supervisor",
        recipient="consultant@swarm-beta",
        header="Request for Analysis",
        body="Please analyze the following data...",
        sender_swarm="swarm-alpha",
        recipient_swarm="swarm-beta"
    ),
    msg_type="request"
)

# Submit to local ACP instance
await acp_instance.submit(message)
```

### Using the HTTP API

```bash
# Register a new swarm
curl -X POST http://localhost:8000/swarms/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "swarm-beta",
    "base_url": "http://localhost:8001",
    "auth_token": "optional-auth-token"
  }'

# Send interswarm message
curl -X POST http://localhost:8000/interswarm/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer user-token" \
  -d '{
    "target_swarm": "swarm-beta",
    "message": "Hello from swarm-alpha!"
  }'

# List known swarms
curl http://localhost:8000/swarms
```

### Agent Tools with Interswarm Support

When interswarm messaging is enabled, agents can use enhanced tools:

```python
# Send message to remote agent
send_request(
    target="consultant@swarm-beta",
    header="Data Analysis Request",
    message="Please analyze the quarterly sales data."
)

# Broadcast to multiple swarms
send_interswarm_broadcast(
    header="System Maintenance",
    message="Scheduled maintenance in 1 hour.",
    target_swarms=["swarm-beta", "swarm-gamma"]
)

# Discover new swarms
discover_swarms(
    discovery_urls=["http://registry.example.com/swarms"]
)
```

## API Endpoints

### Health Check
- `GET /health` - Health check for interswarm communication

### Swarm Management
- `GET /swarms` - List all known swarms
- `POST /swarms/register` - Register a new swarm

### Interswarm Communication
- `POST /interswarm/message` - Receive interswarm message
- `POST /interswarm/send` - Send interswarm message

## Security Considerations

### Authentication
- Use authentication tokens for interswarm communication
- Validate tokens on both sending and receiving sides
- Consider using mutual TLS for additional security

### Network Security
- Use HTTPS for all interswarm communication
- Implement rate limiting to prevent abuse
- Consider using VPNs for private swarm networks

### Message Validation
- Validate message format and content
- Implement message signing for critical communications
- Log all interswarm messages for audit purposes

## Deployment

### Single Swarm Setup

```bash
# Set environment variables
export SWARM_NAME=swarm-alpha
export BASE_URL=http://localhost:8000

# Start the server
uv run -m src.acp.server
```

### Multi-Swarm Setup

```bash
# Terminal 1: Start Swarm Alpha
export SWARM_NAME=swarm-alpha
export BASE_URL=http://localhost:8000
uv run -m src.acp.server

# Terminal 2: Start Swarm Beta
export SWARM_NAME=swarm-beta
export BASE_URL=http://localhost:8001
uv run -m src.acp.server

# Register swarms with each other
curl -X POST http://localhost:8000/swarms/register \
  -H "Content-Type: application/json" \
  -d '{"name": "swarm-beta", "base_url": "http://localhost:8001"}'

curl -X POST http://localhost:8001/swarms/register \
  -H "Content-Type: application/json" \
  -d '{"name": "swarm-alpha", "base_url": "http://localhost:8000"}'
```

## Monitoring and Debugging

### Health Monitoring
- Check `/health` endpoint for swarm status
- Monitor swarm registry for endpoint availability
- Set up alerts for swarm failures

### Logging
- Enable debug logging for interswarm messages
- Monitor HTTP request/response logs
- Track message routing and delivery

### Troubleshooting
- Verify swarm endpoints are accessible
- Check authentication tokens are valid
- Ensure message format is correct
- Monitor network connectivity between swarms

## Best Practices

1. **Naming Conventions**: Use descriptive swarm names and agent names
2. **Error Handling**: Implement proper error handling for network failures
3. **Message Size**: Keep messages reasonably sized for HTTP transport
4. **Rate Limiting**: Implement rate limiting to prevent abuse
5. **Monitoring**: Set up comprehensive monitoring for interswarm communication
6. **Security**: Use authentication and encryption for all interswarm communication
7. **Documentation**: Document swarm interfaces and message formats

## Limitations

- HTTP-based routing adds latency compared to local messaging
- Network failures can cause message delivery failures
- Requires all swarms to be running and accessible
- Authentication and security must be properly configured
- Message ordering is not guaranteed across swarms

## Future Enhancements

- Message queuing and retry mechanisms
- Message encryption and signing
- Load balancing across multiple swarm instances
- Message routing based on content and capabilities
- Integration with service mesh technologies
- Support for WebSocket-based real-time communication
