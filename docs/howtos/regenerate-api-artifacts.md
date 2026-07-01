# Regenerate API Artifacts

Status: draft

## Goal

Refresh the generated files after changing routes, protocol models, the CLI,
docs, or dependencies, and confirm the changes are the ones you expect.

## Starting Point

You changed FastAPI routes, protocol models, CLI parsers, documentation inputs,
or the dependency set, and one or more committed artifacts is now stale.

## Which artifact to regenerate

| You changed… | Regenerate | Output |
| --- | --- | --- |
| Routes, request/response models | OpenAPI | `spec/openapi.yaml` |
| A CLI parser (flags/subcommands) | CLI reference pages | `docs/references/*-cli.md` |
| `README.md` or docs used in the digest | `llms.txt` | `llms.txt` |
| Dependencies | Third-party notices | `THIRD_PARTY_NOTICES.md` |

## Steps

### 1. Regenerate the OpenAPI contract

`spec/openapi.yaml` is generated from the FastAPI app, not hand-edited:

```bash
uv run python scripts/generate_openapi.py
```

It writes `spec/openapi.yaml` by default (pass `--output spec/openapi.json` for
JSON).

### 2. Regenerate the CLI reference pages

The four CLI references are derived from each command's argparse parser:

```bash
uv run python scripts/build_cli_docs.py
```

This rewrites `docs/references/{client,admin,server,daemon}-cli.md`.

### 3. Rebuild `llms.txt`

```bash
uv run python scripts/build_llms_txt.py
```

### 4. Rebuild third-party license notices

```bash
uv run python scripts/build_third_party_licenses.py
```

Writes `THIRD_PARTY_NOTICES.md`.

### 5. Validate

Run the contract tests, which include the OpenAPI drift check:

```bash
uv run pytest -m contract
```

`tests/contract/test_openapi_drift.py` fails if the committed `spec/openapi.yaml`
still differs from the app — regenerate (step 1) until it passes. See
[Run the Test Suite](run-tests.md).

### 6. Review before committing

Generated files can carry incidental churn. Review `git diff` and confirm the
changes match what you intended before committing.

## See also

- [Protocol Specification](../references/protocol-specification.md) — how the
  generated OpenAPI relates to the normative spec.
- [Run the Test Suite](run-tests.md)

## Source Material

- `scripts/generate_openapi.py`
- `scripts/build_cli_docs.py`
- `scripts/build_llms_txt.py`
- `scripts/build_third_party_licenses.py`
