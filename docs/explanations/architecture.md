# Architecture

Status: stub

## Question

How do the active MAIL v2 packages and runtime components fit together?

## Source Material

- `README.md`
- `pyproject.toml`
- `src/mail/protocol/`
- `src/mail/server/`
- `src/mail/client/`
- `src/mail/daemon/`
- `spec/SPEC.md` section 4

## Topics to Discuss

- Protocol package as shared data and network contracts.
- Server package as the HTTP implementation and state owner.
- Client package as the CLI user-agent interface.
- Daemon package as the delivery worker.
- Backend abstraction and current memory backend.
- OpenAPI and contract tests as cross-package alignment points.

## Related Pages

- [Repository Layout](../references/repository-layout.md)
- [HTTP API](../references/http-api.md)
- [Storage Backends](../references/storage-backends.md)
