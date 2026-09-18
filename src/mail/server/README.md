# mail-swarms-server

The FastAPI reference server for the MAIL protocol. It provides authenticated
mailboxes, memory and SQLite storage backends, local daemon delivery, webhooks,
mailing lists, and signed Federation v1 delivery.

```bash
pip install mail-swarms-server
backend-init --type sqlite --host mail.example.com
mail-server --backend sqlite
```

The package also includes `mail-federation-key`, which safely generates and
inspects Ed25519 federation keys:

```bash
mail-federation-key generate ./federation.pem --key-id 2026-09
mail-federation-key inspect ./federation.pem --key-id 2026-09
```

See the repository documentation for [server configuration](../../../docs/references/configuration.md),
[HTTP API](../../../docs/references/http-api.md), [storage backends](../../../docs/references/storage-backends.md),
and the [federation operator guide](../../../docs/howtos/enable-federation.md).
