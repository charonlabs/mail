# MAILClient Guide

`MAILClient` is the reference asynchronous Python client for the MAIL HTTP API. It wraps every documented endpoint, handles bearer authentication, and provides helpers for Server‑Sent Events (SSE) streaming and interswarm routing.

Use this guide when you want to talk to a MAIL server from Python without writing raw `aiohttp` calls.

## Installation & Requirements
- `MAILClient` lives in `src/mail/client.py` and ships with the main package (`pip install -e .` or `uv sync`).
- **Python 3.12+** and **aiohttp** (pulled in automatically via `pyproject.toml`).
- The client is fully asynchronous. Run it inside an asyncio event loop, preferably with `asyncio.run(...)` or within async frameworks such as FastAPI or LangChain tools.

## Quick Start

```python
import asyncio

from mail.client import MAILClient


async def main() -> None:
	async with MAILClient("http://localhost:8000", api_key="user-token") as client:
		root = await client.get_root()
		print(root["version"])

		response = await client.post_message(
			"Hello from MAILClient",
			entrypoint="supervisor",
			show_events=True,
		)
		print(response)

	stream = await client.post_message_stream("Stream this task")
	async for event in stream:
		print(event.event, event.data)


if __name__ == "__main__":
	asyncio.run(main())
```

## Connection Options
- `MAILClient(base_url, api_key=None, timeout=60.0, session=None)`
  - `base_url`: Root URL for the MAIL server (no trailing slash).
  - `api_key`: Optional JWT or API key. When provided, every request includes `Authorization: Bearer <api_key>`.
  - `timeout`: Float seconds or an `aiohttp.ClientTimeout`. Applies to the internally managed session.
  - `session`: Provide your own `aiohttp.ClientSession` to share connections or customise connectors. The client will not close externally supplied sessions.

The class implements `__aenter__` / `__aexit__`, so `async with` automatically opens and closes the HTTP session (`aclose()` is also available).

## Endpoint Coverage

| Category | Methods | Notes |
| --- | --- | --- |
| Service metadata | `get_root()`, `get_status()` | Mirrors `GET /` and `GET /status`. |
| Health | `get_health()` | Returns interswarm readiness info. |
| Messaging | `post_message(message, entrypoint=None, show_events=False)`, `post_message_stream(message, entrypoint=None)` | Handles synchronous responses and SSE streaming. |
| Swarm registry | `get_swarms()`, `register_swarm(...)`, `dump_swarm()`, `load_swarm_from_json(json_str)` | Manage remote swarm entries and persistent templates. |
| Interswarm | `post_interswarm_message(...)`, `post_interswarm_response(...)`, `send_interswarm_message(...)` | Submit or receive interswarm traffic. |

All helpers return deserialised `dict` objects matching the schemas in `spec/openapi.yaml`. For MAIL envelope types (`MAILMessage`, `MAILInterswarmMessage`) the client expects the dictionary shape defined in `mail.core.message`.

## Streaming Responses

`post_message_stream` returns an async iterator over `sse_starlette.ServerSentEvent` instances. Internally, the client parses chunked text from the HTTP response and yields structured events.

```python
stream = await client.post_message_stream("Need live updates")
async for event in stream:
	if event.event == "task_complete":
		print("done", event.data)
```

## Error Handling
- HTTP transport errors raise `RuntimeError` with the originating `aiohttp` exception chained.
- Non‑JSON responses raise `ValueError` annotated with the returned content type and body.
- Always wrap calls in try/except when the network may be flaky or when tokens can expire.

## Testing & Utilities
- Unit coverage lives in `tests/unit/test_mail_client.py`, using an in‑process aiohttp server to validate payloads and streaming behaviour.
- `scripts/demo_client.py` launches a stubbed MAIL server and exercises the client end‑to‑end—useful for manual testing or onboarding demos.

## Integration Tips
- **Reuse sessions** for high‑throughput scenarios by passing an externally managed `ClientSession`.
- **Custom headers**: Extend `_build_headers` by subclassing `MAILClient` if you need additional per‑request metadata.
- **Timeouts**: Provide an `aiohttp.ClientTimeout(total=...)` for fine control over connect/read limits.
- **Logging**: Enable the `mail.client` logger for request traces (`logging.getLogger("mail.client").setLevel(logging.DEBUG)`).

## Related Documentation
- [API Surfaces](./api.md) – discusses the HTTP routes that `MAILClient` calls.
- [Quickstart](./quickstart.md) – shows how to run the server; you can replace `curl` steps with `MAILClient` snippets.
- [Testing](./testing.md) – outlines the project’s testing strategy, including client exercises.
- [Troubleshooting](./troubleshooting.md) – consult for common connectivity issues.
