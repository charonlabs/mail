# Federation Key CLI

Status: generated

> **Generated file — do not edit by hand.** Regenerate with `uv run python scripts/build_cli_docs.py` after changing the CLI. See [Regenerate API Artifacts](../howtos/regenerate-api-artifacts.md).

Generate or inspect a MAIL Federation v1 Ed25519 key

Invoke as `mail-federation-key` (or `uv run mail-federation-key` from a workspace checkout). Source: `mail_server/federation/key_cli.py`.

## Global options

- `--license` — show license information and exit

## Commands

### `generate`

generate a federation signing key

**Arguments:**

- `path` — path to the unencrypted Ed25519 private-key PEM

**Options:**

- `--key-id` `KEY_ID` — public key identifier advertised in the federation manifest
- `--json` — print the public key record as JSON

### `inspect`

inspect a federation signing key

**Arguments:**

- `path` — path to the unencrypted Ed25519 private-key PEM

**Options:**

- `--key-id` `KEY_ID` — public key identifier advertised in the federation manifest
- `--json` — print the public key record as JSON
