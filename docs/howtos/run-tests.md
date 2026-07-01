# Run the Test Suite

Status: draft

## Goal

Run the active MAIL v2 tests, focus on a subset, measure coverage, and run the
archived v1 tests when needed.

## Starting Point

Workspace dependencies are installed (`uv sync`).

## Steps

### 1. Run the active suite

```bash
uv run pytest
```

This runs everything under `tests/` **except** the `e2e` group (excluded by
default in `pytest.ini`).

### 2. Run a subset

Tests are marked by category — `unit`, `integration`, `contract`, `e2e` — and
also live in matching directories. Select by marker or by path:

```bash
uv run pytest -m unit                 # pure-logic tests
uv run pytest -m contract             # spec/OpenAPI conformance
uv run pytest tests/integration       # by directory
uv run pytest -m e2e                  # full-system subprocess tests (opt-in)
```

Integration and contract tests run against **both** the memory and SQLite
backends via a parametrized fixture, so a green run exercises both stores.

### 3. Measure coverage

Coverage is scoped to the v2 packages (configured in `pyproject.toml`):

```bash
uv run pytest --cov
```

### 4. Run the archived v1 tests (only when needed)

Legacy tests are not part of the default run and need the `legacy` extra:

```bash
uv run --extra legacy pytest src/mail/legacy/tests
```

See [MAIL v1 Legacy Runtime](../explanations/mail-v1-legacy.md).

## Interpreting results

- **OpenAPI drift** (`tests/contract/test_openapi_drift.py`) fails when the
  committed `spec/openapi.yaml` no longer matches the app — regenerate it (see
  [Regenerate API Artifacts](regenerate-api-artifacts.md)).
- **Contract tests** (`tests/contract/`) enforce SPEC.md rules on addresses,
  messages, and delivery; a failure means the implementation diverged from the
  spec. See [Protocol Specification](../references/protocol-specification.md).
- **Expected `xfail`s** in `tests/integration/test_stubs.py` mark operations that
  are `NotImplementedError` on the memory backend (message deletion, trash clear,
  webhook patch, remote delivery) — these are implemented on SQLite. An `xpass`
  there means one was implemented and the marker should be removed.

## Source Material

- `pytest.ini`
- `tests/`
- `src/mail/legacy/tests/`
- `pyproject.toml` (`[tool.coverage]`)
