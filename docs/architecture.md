# Architecture

This section explains the runtime, server, and networking layers that make up a MAIL swarm.

## Overview
- **Runtime**: per-user (or per-swarm) message queue, agents, tools, and execution ([src/mail/core/runtime.py](/src/mail/core/runtime.py))
- **API/Server**: FastAPI app exposing HTTP endpoints and managing persistent templates and user-scoped instances ([src/mail/server.py](/src/mail/server.py), [src/mail/api.py](/src/mail/api.py))
- **Interswarm**: HTTP router and registry for cross-swarm messaging ([src/mail/net/router.py](/src/mail/net/router.py), [src/mail/net/registry.py](/src/mail/net/registry.py))

## Key concepts
- **`MAILMessage`**: canonical envelope for request/response/broadcast/interrupt; see [message-format.md](/docs/message-format.md) and [src/mail/core/message.py](/src/mail/core/message.py)
- **Agents**: async callables that produce text + tool calls; created by factories, which can be configured in [swarms.json](/swarms.json)
- **Actions/Tools**: structured tool specs that let agents send MAIL messages, broadcast, interrupt, and complete tasks
- **Swarm**: a set of agents plus optional actions, with a directed communication graph and a designated entrypoint

## Runtime
- **Message queue**: priority queue with deterministic tie-breaking; processes messages and schedules tool execution
- **Agent histories**: maintained per agent for context and multi-turn behavior
- **Pending requests**: tracked futures keyed by task_id for correlating final responses and streaming
- **Events and SSE**: events are collected and streamed via Server-Sent Events (SSE) with heartbeat pings
- **Interswarm**: optional router that detects `agent@swarm` recipients and routes over HTTP

## Server and API
- **Persistent template**: built at startup from [swarms.json](/swarms.json) into `MAILSwarmTemplate`
- **User isolation**: each authenticated user gets a dedicated `MAILSwarm` instance with its own runtime loop
- **Endpoints**: `GET /`, `GET /status`, `POST /message` (+SSE), interswarm endpoints, and registry management; see [api.md](/docs/api.md)
- **Lifespan**: on startup, initializes registry, loads the persistent swarm, and starts health checks; on shutdown, cleans up instances and saves persistent registry state

## Interswarm
- **Router**: inspects recipient addresses; local vs remote routing; wraps messages into `MAILInterswarmMessage` for HTTP
- **Registry**: tracks local/remote swarms, performs health checks, stores persistent endpoints, supports env-backed auth tokens
- **Addressing**: use `agent@swarm` to target remote swarms; local addresses use just `agent`

## Files to read
- **Runtime and tools**: [src/mail/core/runtime.py](/src/mail/core/runtime.py), [src/mail/core/tools.py](/src/mail/core/tools.py)
- **HTTP Server**: [src/mail/server.py](/src/mail/server.py)
- **Interswarm types**: [src/mail/net/types.py](/src/mail/net/types.py)
- **Router and registry**: [src/mail/net/router.py](/src/mail/net/router.py), [src/mail/net/registry.py](/src/mail/net/registry.py)
- **Message types**: [src/mail/core/message.py](/src/mail/core/message.py)

