# MAIL Python Reference Implementation Documentation

This folder documents the **Multi‑Agent Interface Layer (MAIL) reference implementation** found in this repository. It explains what MAIL is, how this Python implementation is structured, how to run it, and how to extend it with your own agents and swarms.

If you’re new, start with [Quickstart](/docs/quickstart.md), then read [Architecture](/docs/architecture.md) and [Agents & Tools](/docs/agents-and-tools.md). The [API](/docs/api.md) doc covers both HTTP and Python surfaces, [Client](/docs/client.md) explains the asynchronous HTTP helper, and [Message Format](/docs/message-format.md) specifies the wire schema used by every transport.

## Contents
- **Quickstart**: [quickstart.md](/docs/quickstart.md)
- **Docker Deployment**: [docker.md](/docs/docker.md)
- **Architecture**: [architecture.md](/docs/architecture.md)
- **Configuration**: [configuration.md](/docs/configuration.md)
- **Database Persistence**: [database.md](/docs/database.md)
- **API (HTTP & Python)**: [api.md](/docs/api.md)
- **CLI**: [cli.md](/docs/cli.md)
- **HTTP Client**: [client.md](/docs/client.md)
- **Message Format**: [message-format.md](/docs/message-format.md)
- **Agents & Tools**: [agents-and-tools.md](/docs/agents-and-tools.md)
- **Interswarm Messaging**: [interswarm.md](/docs/interswarm.md)
- **Swarm Registry**: [registry.md](/docs/registry.md)
- **Standard Library**: [stdlib/README.md](/docs/stdlib/README.md)
- **Security**: [security.md](/docs/security.md)
- **Testing**: [testing.md](/docs/testing.md)
- **Examples**: [examples.md](/docs/examples.md)
- **Troubleshooting**: [troubleshooting.md](/docs/troubleshooting.md)

## What is MAIL?
- **MAIL** (**M**ulti‑**A**gent **I**nterface **L**ayer) is a protocol and reference implementation that standardizes how autonomous agents communicate, coordinate, and collaborate.
- The Python implementation uses FastAPI for HTTP endpoints, an internal runtime loop for message processing, and a registry/router for inter‑swarm communication over HTTP.
- The normative protocol specification lives in [spec/](/spec/SPEC.md) and includes JSON Schemas and an OpenAPI file for the HTTP surface.

## Where to look in the code
- **Server and API**: [src/mail/server.py](/src/mail/server.py), [src/mail/api.py](/src/mail/api.py)
- **HTTP client**: [src/mail/client.py](/src/mail/client.py)
- **Core runtime, tools, messages**: [src/mail/core/runtime.py](/src/mail/core/runtime.py), [src/mail/core/tools.py](/src/mail/core/tools.py), [src/mail/core/message.py](/src/mail/core/message.py)
- **Interswarm**: [src/mail/net/router.py](/src/mail/net/router.py), [src/mail/net/registry.py](/src/mail/net/registry.py), [src/mail/net/types.py](/src/mail/net/types.py)
- **Utilities**: [src/mail/utils/](/src/mail/utils/__init__.py)
- **Examples and agent functions**: [src/mail/examples/](/src/mail/examples/__init__.py), [src/mail/factories/](/src/mail/factories/__init__.py)
