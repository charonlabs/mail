# Interswarm Response Flow

This document explains how responses flow between different ACP swarms when using interswarm messaging.

## Overview

When Swarm A sends a message to Swarm B, the response from Swarm B needs to be properly routed back to Swarm A and fed into its local ACP instance. This document describes the complete flow.

## Message Flow

### 1. Swarm A → Swarm B (Request)

1. **User in Swarm A** sends a message via `/chat` endpoint
2. **Swarm A ACP** creates a message with recipient `agent@swarm-b`
3. **Interswarm Router** detects remote recipient and routes via HTTP
4. **HTTP POST** to `swarm-b:8000/interswarm/message`
5. **Swarm B** receives message and processes it via local ACP

### 2. Swarm B → Swarm A (Response)

1. **Swarm B ACP** generates response after processing
2. **Swarm B** creates response message with `sender_swarm: swarm-b`
3. **HTTP POST** to `swarm-a:8000/interswarm/response`
4. **Swarm A** receives response via `/interswarm/response` endpoint
5. **Swarm A** finds appropriate ACP instance using `task_id`
6. **Response** is fed back into Swarm A's ACP instance

## Key Components

### Server Endpoints

- `/interswarm/message` - Receives messages from other swarms
- `/interswarm/response` - Receives responses from other swarms
- `/interswarm/send` - Sends messages to other swarms

### Core ACP Methods

- `handle_interswarm_response()` - Handles incoming responses from remote swarms
- `_route_interswarm_message()` - Routes messages to remote swarms
- `submit_and_wait()` - Waits for responses to complete

### Interswarm Router

- Routes messages between local and remote swarms
- Handles HTTP communication between swarms
- Manages swarm registry and endpoint discovery

## Example Flow

```
Swarm A (localhost:8000)                    Swarm B (localhost:8001)
┌─────────────────┐                        ┌─────────────────┐
│ User sends msg  │                        │                 │
│ to agent@swarm-b│                        │                 │
└─────────┬───────┘                        └─────────────────┘
          │
          ▼
┌─────────────────┐
│ ACP creates msg │
│ with remote     │
│ recipient       │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Interswarm      │
│ Router detects  │
│ remote swarm    │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐                        ┌─────────────────┐
│ HTTP POST to    │───────────────────────▶│ /interswarm/    │
│ swarm-b:8001/   │                        │ message         │
│ interswarm/     │                        └─────────┬───────┘
│ message         │                        │         │
└─────────────────┘                        │         ▼
          │                                │ ┌───────────────┐
          │                                │ │ Swarm B ACP   │
          │                                │ │ processes msg │
          │                                │ └───────┬───────┘
          │                                │         │
          │                                │         ▼
          │                                │ ┌───────────────┐
          │                                │ │ Response      │
          │                                │ │ generated     │
          │                                │ └───────┬───────┘
          │                                │         │
          │                                │         ▼
          │                                │ ┌───────────────┐
          │                                │ │ HTTP POST to  │
          │                                │ │ swarm-a:8000/ │
          │                                │ │ interswarm/   │
          │                                │ │ response      │
          │                                │ └───────┬───────┘
          │                                │         │
          ▼                                │         │
┌─────────────────┐                        │         │
│ /interswarm/    │◀───────────────────────┘         │
│ response        │                                    │
└─────────┬───────┘                                    │
          │                                            │
          ▼                                            │
┌─────────────────┐                                    │
│ Find ACP        │                                    │
│ instance by     │                                    │
│ task_id         │                                    │
└─────────┬───────┘                                    │
          │                                            │
          ▼                                            │
┌─────────────────┐                                    │
│ Feed response   │                                    │
│ back into       │                                    │
│ local ACP       │                                    │
└─────────────────┘                                    │
```

## Configuration

### Environment Variables

- `SWARM_NAME` - Name of the local swarm
- `BASE_URL` - Base URL for the local swarm server

### Swarm Registry

Swarms register themselves with each other for discovery:

```bash
# Register Swarm B with Swarm A
curl -X POST http://localhost:8000/swarms/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "swarm-b",
    "base_url": "http://localhost:8001",
    "auth_token": "optional-auth-token"
  }'
```

## Testing

1. Start two ACP servers on different ports
2. Register swarms with each other
3. Send a message from one swarm to another
4. Verify the response flows back correctly

## Troubleshooting

- Check that both swarms are registered in each other's registries
- Verify HTTP endpoints are accessible between swarms
- Check logs for routing and response handling errors
- Ensure task_id consistency between request and response
