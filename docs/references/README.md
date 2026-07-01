# Reference

Reference pages describe MAIL machinery: commands, endpoints, models,
configuration, repository layout, and implementation-defined behavior.
Reference material should be terse, structured consistently, and tied to source
files or generated contracts.

## Planned Reference Pages

| Page | Describes | Source of truth |
| --- | --- | --- |
| [Repository Layout](repository-layout.md) | Active workspace, specs, tests, scripts, and legacy code. | `README.md`, `pyproject.toml` |
| [Configuration](configuration.md) | Environment variables and runtime settings. | CLI modules, `.env.example` |
| [Protocol Specification](protocol-specification.md) | Normative MAIL protocol documents. | `spec/SPEC.md`, `spec/openapi.yaml` |
| [HTTP API](http-api.md) | REST endpoints, auth, request and response bodies. | `spec/openapi.yaml`, FastAPI routers |
| [Client CLI](client-cli.md) | `mail` commands and options. | `src/mail/client/src/mail_client/cli.py` |
| [Admin CLI](admin-cli.md) | Administrator commands and options. | `src/mail/client/src/mail_client/admin_panel.py` |
| [Server CLI](server-cli.md) | `mail-server` options. | `src/mail/server/src/mail_server/cli.py` |
| [Daemon CLI](daemon-cli.md) | `mail-daemon` options and env vars. | `src/mail/daemon/src/mail_daemon/cli.py` |
| [Data Models](data-models.md) | Pydantic models used by protocol and network contracts. | `src/mail/protocol/src/mail_protocol/` |
| [Storage Backends](storage-backends.md) | Backend interfaces and memory backend behavior. | `src/mail/server/src/mail_server/backends/` |

## Reference Checklist

- Match structure to code structure where practical.
- Prefer tables for options, fields, and endpoint summaries.
- Include examples only to clarify syntax.
- Link to tutorials and how-tos instead of becoming step-by-step guidance.
- Update reference pages in the same change as command, API, or model changes.
