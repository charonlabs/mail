> Archived legacy documentation: these pages describe the MAIL v1 runtime now stored under `src/mail/legacy`. Some historical links may still reference the old root layout.

# MAIL Python Reference Implementation Documentation

This folder documents the **Multi‑Agent Interface Layer (MAIL) reference implementation** found in this repository. It explains what MAIL is, how this Python implementation is structured, how to run it, and how to extend it with your own agents and swarms.

If you’re new, start with [Quickstart](quickstart.md), then read [Architecture](architecture.md) and [Agents & Tools](agents-and-tools.md). The [API](api.md) doc covers both HTTP and Python surfaces, [Client](client.md) explains the asynchronous HTTP helper, and [Message Format](message-format.md) specifies the wire schema used by every transport.

## Contents
- **Quickstart**: [quickstart.md](quickstart.md)
- **Docker Deployment**: [docker.md](docker.md)
- **Architecture**: [architecture.md](architecture.md)
- **Configuration**: [configuration.md](configuration.md)
- **Database Persistence**: [database.md](database.md)
- **API (HTTP & Python)**: [api.md](api.md)
- **CLI**: [cli.md](cli.md)
- **HTTP Client**: [client.md](client.md)
- **Message Format**: [message-format.md](message-format.md)
- **Agents & Tools**: [agents-and-tools.md](agents-and-tools.md)
- **Interswarm Messaging**: [interswarm.md](interswarm.md)
- **Swarm Registry**: [registry.md](registry.md)
- **Standard Library**: [stdlib/README.md](stdlib/README.md)
- **Security**: [security.md](security.md)
- **Testing**: [testing.md](testing.md)
- **Examples**: [examples.md](examples.md)
- **Troubleshooting**: [troubleshooting.md](troubleshooting.md)

## What is MAIL?
- **MAIL** (**M**ulti‑**A**gent **I**nterface **L**ayer) is a protocol and reference implementation that standardizes how autonomous agents communicate, coordinate, and collaborate.
- The Python implementation uses FastAPI for HTTP endpoints, an internal runtime loop for message processing, and a registry/router for inter‑swarm communication over HTTP.
- The normative protocol specification lives in [spec/](/spec/SPEC.md) and includes JSON Schemas and an OpenAPI file for the HTTP surface.

## Where to look in the code
- **Server and API**: [src/mail/legacy/server.py](/src/mail/legacy/server.py), [src/mail/legacy/api.py](/src/mail/legacy/api.py)
- **HTTP client**: [src/mail/legacy/client.py](/src/mail/legacy/client.py)
- **Core runtime, tools, messages**: [src/mail/legacy/core/runtime.py](/src/mail/legacy/core/runtime.py), [src/mail/legacy/core/tools.py](/src/mail/legacy/core/tools.py), [src/mail/legacy/core/message.py](/src/mail/legacy/core/message.py)
- **Interswarm**: [src/mail/legacy/net/router.py](/src/mail/legacy/net/router.py), [src/mail/legacy/net/registry.py](/src/mail/legacy/net/registry.py), [src/mail/legacy/net/types.py](/src/mail/legacy/net/types.py)
- **Utilities**: [src/mail/legacy/utils/](/src/mail/legacy/utils/__init__.py)
- **Examples and agent functions**: [src/mail/legacy/examples/](/src/mail/legacy/examples/__init__.py), [src/mail/legacy/factories/](/src/mail/legacy/factories/__init__.py)
