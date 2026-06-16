# Storage Backends

Status: stub

## Scope

Describe the server backend interface and the memory backend persistence
behavior.

## Source of Truth

- `src/mail/server/src/mail_server/backends/base.py`
- `src/mail/server/src/mail_server/backends/memory/`
- `src/mail/server/src/mail_server/backend_init.py`
- `tests/unit/test_memory_fs_roundtrip.py`
- `tests/unit/test_memory_checkpointing.py`

## Entries to Cover

- Backend lifecycle hooks.
- User-agent storage.
- Box storage.
- Draft and trash behavior.
- Message delivery buffer.
- Memory backend filesystem layout.
- Checkpoint behavior.
- Current backend limitations.

## Maintenance Notes

Keep production deployment advice in how-to or explanation pages unless it is a
direct backend capability or limitation.
