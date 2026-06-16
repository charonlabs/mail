# Run the Test Suite

Status: stub

## Goal

How to run the active MAIL v2 test suite, focused test groups, contract tests,
and archived v1 tests when needed.

## Starting Point

The workspace dependencies are installed.

## Source Material

- `pytest.ini`
- `tests/`
- `src/mail/legacy/tests/`
- `pyproject.toml`

## Steps to Cover

1. Run all active v2 tests with `uv run pytest`.
2. Run unit, integration, contract, or end-to-end subsets.
3. Run coverage with the configured source packages.
4. Run archived v1 tests with the `legacy` extra when needed.
5. Interpret failures from OpenAPI drift and protocol contract tests.

## Validation

The selected test command exits successfully and any expected skipped or xfailed
tests are understood.
