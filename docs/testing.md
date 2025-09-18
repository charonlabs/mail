# Testing

## Overview
- **Runner**: `pytest`
- **Layout**: [tests/mock](/tests/mock/) (unit), [tests/network](/tests/network) (API), [tests/unit](/tests/unit/) (core)
- **Config**: [pytest.ini](/pytest.ini)

## Running
- Install dev deps and run: `pytest -q`

## Fixtures & patterns (see [tests/](/tests/))
- Network tests use **FastAPI TestClient** and patch external I/O
- **Fixtures** patch `SwarmRegistry`, auth helpers, and factory imports to avoid network/LLM calls
- **No real external requests** are performed during tests

## Extending
- **Follow existing patterns** under [tests/unit](/tests/unit/) and [tests/network](/tests/network/)
- Reuse provided fixtures for isolated behavior

