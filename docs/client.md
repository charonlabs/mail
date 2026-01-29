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
        root = await client.ping()
        print(root["protocol_version"])

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
- `MAILClient(base_url, api_key=None, session=None, config=None)`
  - `base_url`: Root URL for the MAIL server (no trailing slash). Supports standard HTTP/HTTPS URLs.
  - `api_key`: Optional JWT or API key. When provided, every request includes `Authorization: Bearer <api_key>`.
  - `session`: Provide your own `aiohttp.ClientSession` to share connections or customise connectors. The client will not close externally supplied sessions.
  - `config`: Pass a `ClientConfig` instance (for example `ClientConfig(timeout=120.0, verbose=True)`) to reuse or override defaults hydrated from `mail.toml`.

The class implements `__aenter__` / `__aexit__`, so `async with` automatically opens and closes the HTTP session (`aclose()` is also available).

### `swarm://` URL Support

The CLI client (`mail client`) supports `swarm://` URLs for convenient connection sharing:

```bash
# Connect using swarm:// URL
uv run mail client "swarm://connect?server=example.com&token=my-api-key"
```

The URL is automatically parsed and converted:
- `server` parameter becomes the HTTPS base URL
- `token` parameter is used as the API key (if not overridden by `--api-key`)

Supported URL formats:
```
swarm://connect?server=<hostname>&token=<api_key>
swarm://invite?server=<hostname>&token=<api_key>
```

See [cli.md](./cli.md) for more details on URL scheme handling and OS registration.

### ClientConfig and mail.toml
- `ClientConfig` pulls its defaults from the `[client]` table in `mail.toml` (`timeout` and `verbose`).
- `MAILClient` uses these defaults automatically when you omit the `config` argument; the CLI REPL (`mail client`) follows the same behavior.
- Override per run by constructing `ClientConfig(timeout=..., verbose=...)` or by exporting/pointing `MAIL_CONFIG_PATH` to an alternate config file.

## Endpoint Coverage

| Category | Methods | Notes |
| --- | --- | --- |
| Service metadata | `ping()`, `get_status()` | Mirrors `GET /` and `GET /status`. |
| Identity | `get_whoami()` | Fetches the caller's username and role via `GET /whoami`. |
| Health | `get_health()` | Returns interswarm readiness info. |
| Messaging | `post_message(message, entrypoint=None, show_events=False)`, `post_message_stream(message, entrypoint=None)` | Handles synchronous responses and SSE streaming. |
| Task inspection | `get_tasks()`, `get_task(task_id)` | Fetch task overviews or a full record using `GET /tasks` and `GET /task`. |
| Swarm registry | `get_swarms()`, `register_swarm(...)`, `dump_swarm()`, `load_swarm_from_json(json_str)` | Manage remote swarm entries and persistent templates. |
| Interswarm | `post_interswarm_message(...)`, `post_interswarm_response(...)`, `send_interswarm_message(...)` | Submit or receive interswarm traffic. |
| Debug/OpenAI | `debug_post_responses(input, tools, instructions=None, previous_response_id=None, tool_choice=None, parallel_tool_calls=None, **kwargs)` | Calls the debug-only `/responses` endpoint; requires server debug mode. |

All helpers return deserialized `dict` objects matching the schemas in `spec/openapi.yaml`. For MAIL envelope types (`MAILMessage`, `MAILInterswarmMessage`) the client expects the dictionary shape defined in `mail.core.message`.

## Streaming Responses

`post_message_stream` returns an async iterator over `sse_starlette.ServerSentEvent` instances. Internally, the client parses chunked text from the HTTP response and yields structured events.

```python
stream = await client.post_message_stream("Need live updates")
async for event in stream:
    if event.event == "task_complete":
        print("done", event.data)
```

## Task Lifecycle and Resuming Previous Tasks

- Every call to `post_message`/`post_message_stream` participates in a **task** identified by `task_id`. If you omit the field, the server generates an ID. Reuse the same `task_id` to continue the conversation (for example, when running the runtime in continuous mode).
- When an agent invokes a tool that has been marked as a **breakpoint tool**, the runtime pauses the task and waits for the caller to provide the tool result. Resume the task by sending another message with:
  - The original `task_id`.
  - `resume_from="breakpoint_tool_call"`.
  - Extra keyword argument `breakpoint_tool_call_result`, a JSON string describing the tool outputs. Provide either a single object (`{"content": "..."}`) or a list of objects (`[{"call_id": "...", "content": "..."}]`) when multiple breakpoint tool calls paused in parallel.

```python
import json

task_id = "weather-task"

# Start a new task (runtime will mark it running until completion or a breakpoint)
response = await client.post_message(
    "Plan tomorrow's rehearsal dinner",
    task_id=task_id,
    entrypoint="supervisor",
)

# Later, resume the task after the breakpoint tool returns a value
stream = await client.post_message_stream(
    "Continuing after breakpoint",
    task_id=task_id,
    resume_from="breakpoint_tool_call",
    breakpoint_tool_call_result=json.dumps(
        {"call_id": "bp-1", "content": "Forecast: sunny with a high of 75°F"}
    ),
)
async for event in stream:
    ...
```

- The other supported value of `resume_from` is `"user_response"`. Use this for handling cases when a user wants to follow up on a previous task.
  - Note that the `msg_type` of a `user_response` *does not necessarily* need to be a `response`--the default message type is `request`, which works perfectly fine here.

```python
task_id = "weather-task-2"

response = await client.post_message(
    "What will the weather in San Francisco be tomorrow?",
    task_id=task_id,
)

follow_up = await client.post_message(
    "How does that compare to the forecast for Los Angeles?",
    task_id=task_id,
    resume_from="user_response",
) # msg_type = "request" here
```

- The runtime automatically resumes the task loop, restores any stashed queue items for that task, re-hydrates the agent history with the tool output, and emits the usual `task_complete` event once the agents finish.

Use the new inspection helpers to audit active or completed work:

```python
tasks = await client.get_tasks()
for task_id, task in tasks.items():
    print(task_id, task["completed"], task["is_running"])

latest = await client.get_task(task_id="weather-task")
print(latest["events"][-1]["event"])
```

Both helpers require the caller to own the task; the server automatically scopes results to the authenticated user/admin.

## OpenAI Responses bridge

- Enable server debug mode (`mail server --debug` or `[server].debug = true`) before calling `debug_post_responses`. This instantiates the internal OpenAI bridge (`SwarmOAIClient`) and exposes `/responses`.
- The helper expects the same payload shape as OpenAI's Responses API.
- Any extra keyword arguments (for example, `"parallel_tool_calls"` overrides or custom metadata) are forwarded verbatim inside the request body and handed to `SwarmOAIClient` for execution.
- Example (assuming you already have an authenticated `MAILClient` instance named `client`):

  ```python
  response = await client.debug_post_responses(
      input=[
          {"role": "system", "content": "You orchestrate the MAIL swarm."},
          {"role": "user", "content": "Draft a response for tomorrow's stand-up."}
      ],
      tools=[],
  )
  print(response.output)
  ```

- The CLI exposes the same workflow with `mail client responses …`; see [cli.md](./cli.md) for the REPL syntax.

## Error Handling

- HTTP transport errors raise `RuntimeError` with the originating `aiohttp` exception chained.
- Non‑JSON responses raise `ValueError` annotated with the returned content type and body.
- Always wrap calls in `try/except` when the network may be flaky or when tokens can expire.

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
