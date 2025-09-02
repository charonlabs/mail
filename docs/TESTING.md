Testing Guide

Overview
- Runner: pytest
- Layout: tests/mock for isolated unit tests, tests/network for API tests
- Config: pytest.ini at repo root

Running Tests
- Install dev dependencies for your environment (pytest, httpx/requests not required beyond FastAPI's TestClient).
- Run: `pytest`

Test Types
- Mock tests: Validate helpers and core orchestration without network or LLMs. These use stub agents and fake registries.
- Network tests: Exercise FastAPI endpoints using TestClient with the app's lifespan, patched to avoid real external calls.

Fixtures
- `patched_server`: Patches `SwarmRegistry`, `build_swarm_from_name`, and auth helpers to avoid network and heavyweight models.
- `set_auth_env`: Forces AUTH/TOKEN endpoints to dummy values to guard accidental I/O.

Notes
- No external network calls are performed; interswarm/health checks are disabled in tests.
- If you want to extend coverage, add further tests under each section and reuse provided fixtures.

