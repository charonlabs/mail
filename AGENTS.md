# MAIL v2 Agent Notes

This repository is in the middle of the MAIL v2 reorganization. Treat the v2
workspace packages as the active implementation and `src/mail/legacy` as the
archived MAIL v1 runtime.

## Active Layout

```text
src/mail/protocol/   # mail-protocol: shared protocol models/constants
src/mail/server/     # mail-server: FastAPI server
src/mail/client/     # mail-client: CLI/client
src/mail/daemon/     # mail-daemon: daemon implementation
src/mail/legacy/     # archived MAIL v1 runtime and related material
```

Root-level `docs/` is for v2 repository docs. Archived v1 docs, config, UI, and
old onboarding notes live under `src/mail/legacy`.

## Commands

```bash
uv sync
uv run mail-server --help
uv run mail --help
uv run pytest
uv run pytest src/mail/legacy/tests
```

During migration, some root-level scripts still target legacy modules.
Root `tests/` is the active v2 suite; legacy tests run explicitly from `src/mail/legacy/tests`.

## Import Guidance

Use v2 package imports for new work:

```python
import mail_protocol
import mail_server
import mail_client
import mail_daemon
```

Use `mail.legacy.*` only for archived v1 code or compatibility work. Avoid
adding new v2 behavior to `mail.legacy`.

## Documentation

- Root v2 docs: `docs/README.md`
- Server docs: `src/mail/server/docs/README.md`
- Client docs: `src/mail/client/docs/README.md`
- Legacy runtime notes: `src/mail/legacy/README.md`

