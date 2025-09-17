# MAIL Documentation

This folder documents the **Multi‑Agent Interface Layer (MAIL)** reference implementation found in this repository. It explains what MAIL is, how this Python implementation is structured, how to run it, and how to extend it with your own agents and swarms.

If you’re new, start with [Quickstart](/docs/quickstart.md), then read [Architecture](/docs/architecture.md) and [Agents & Tools](/docs/agents-and-tools.md). The [API](/docs/api.md) and [Message Format](/docs/message-format.md) docs specify how to integrate clients and other swarms.

## Contents
- **Quickstart**: quickstart.md
- **Architecture**: architecture.md
- **Configuration**: configuration.md
- **API (HTTP)**: api.md
- **Message Format**: message-format.md
- **Agents & Tools**: agents-and-tools.md
- **Interswarm Messaging**: interswarm.md
- **Swarm Registry**: registry.md
- **Security**: security.md
- **Testing**: testing.md
- **Examples**: examples.md
- **Troubleshooting**: troubleshooting.md

## What is MAIL?
- MAIL (Multi‑Agent Interface Layer) is a protocol and reference implementation that standardizes how autonomous agents communicate, coordinate, and collaborate.
- The Python implementation uses FastAPI for HTTP endpoints, an internal runtime loop for message processing, and a registry/router for inter‑swarm communication over HTTP.
- The normative protocol specification lives in `spec/` and includes JSON Schemas and an OpenAPI file for the HTTP surface.

## Where to look in the code
- **Server and API**: [src/mail/server.py](/src/mail/server.py), [src/mail/api.py](/src/mail/api.py)
- **Core runtime, tools, messages**: [src/mail/core/runtime.py](/src/mail/core/runtime.py), [src/mail/core/tools.py](/src/mail/core/tools.py), [src/mail/core/message.py](/src/mail/core/message.py)
- **Interswarm**: [src/mail/net/router.py](/src/mail/net/router.py), [src/mail/net/registry.py](/src/mail/net/registry.py), [src/mail/net/types.py](/src/mail/net/types.py)
- **Utilities**: [src/mail/utils/](/src/mail/utils/__init__.py)
- **Examples and factories**: [src/mail/examples/](/src/mail/examples/__init__.py), [src/mail/factories/](/src/mail/factories/__init__.py)

