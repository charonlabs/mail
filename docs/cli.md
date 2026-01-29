# MAIL Command-Line Interface

The reference implementation ships with a convenience CLI that lets you run the FastAPI server and talk to it interactively from the same entry point. Both commands are exposed via the console script `mail`, which is installed when you install this package (`uv sync` or `pip install -e .`).

## Commands

```shell
mail server   # run the FastAPI reference server
mail client   # launch the interactive MAIL client REPL
mail version  # print MAIL reference + protocol version information
mail ping     # check if a MAIL server is reachable
mail db-init  # initialize database tables for persistence
mail register # register as OS handler for swarm:// URLs
```

The top-level parser accepts the same flags regardless of how you invoke it, for example `python -m mail.cli …` or `uv run mail …`. Use `mail version` any time you need to confirm the reference implementation and protocol version advertised by the CLI.

### `mail server`
- Configuration defaults are read from `mail.toml` (see
  [configuration.md](./configuration.md)). Flags such as `--host`, `--port`, `--reload`, `--swarm-name`, `--swarm-source`, and `--swarm-registry` only override the values you provide.
- Use `--config /path/to/mail.toml` to point at a different   configuration file for a single run. The environment variable `MAIL_CONFIG_PATH` acts as the persistent override if you prefer exporting it once.
- Environment variables such as `AUTH_ENDPOINT` and `TOKEN_INFO_ENDPOINT` remain required; `LITELLM_PROXY_API_BASE` is required only if your swarm uses `use_proxy=true`. The CLI does not provide defaults for these. When launched via `mail server`, defaults from `mail.toml` are exported to `SWARM_NAME`, `SWARM_SOURCE`, `SWARM_REGISTRY_FILE`, and `BASE_URL` for you.
- Pass `--debug` (or set `[server].debug = true`) when you need the debug-only surface, including the OpenAI-compatible `/responses` endpoint. Leave it off for production deployments.
- Example:

  ```bash
  uv run mail server \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
  ```

### `mail client`
Launching `mail client` starts the interactive REPL.

- Provide the server URL as the first positional argument so the client knows which base URL to contact; the CLI does not infer it automatically.
- The default timeout comes from the `[client]` table in `mail.toml`; override it per invocation with `--timeout`.
- The `--config` flag is shared with `mail server`, allowing you to point both commands at the same config file if you keep multiple TOML profiles.
- Toggle verbose HTTP logging for the REPL with `--verbose`; it mirrors `[client].verbose` from `mail.toml`.

```shell
uv run mail client http://localhost:8000 \
--api-key $USER_TOKEN
```

Once inside you will see the prompt `mail>`. The REPL accepts any of the subcommands documented in [docs/client.md](./client.md), plus a few helper commands:

| Command | Description |
| --- | --- |
| `help` / `?` | Print CLI usage information without exiting the loop. |
| `exit` / `quit` | Leave the REPL. |
| `ping` | Invoke `GET /` and display the server name/version. |
| `health [-v]` / `health-update STATUS` | Read or update health probes (update requires admin role). |
| `whoami`, `status`, `login`, `logout` | Inspect or change the caller identity tracked by the session. |
| `message "…" [--entrypoint …] [--task-id …] [--resume-from …] [--kwargs '{…}'] [--show-events]` | Submit a message and print the structured response. |
| `message-stream "…" [--task-id …] [--resume-from …] [--kwargs '{…}']` | Stream SSE events; each event is printed as it arrives. |
| `message-interswarm "…" '["agent@remote"]' $USER_TOKEN` | Proxy a request to another swarm (requires interswarm). |
| `swarms-get`, `swarm-register`, `swarm-dump`, `swarm-load-from-json` | Inspect or mutate the swarm registry and persistent template. |
| `responses INPUT TOOLS [--instructions …] [--previous-response-id …] [--tool-choice …] [--parallel-tool-calls] [--kwargs '{…}']` | Debug-only OpenAI `/responses` call; requires the server to run with `--debug` and a JSON payload for `INPUT`/`TOOLS`. |

The REPL uses `shlex.split`, so quoting works as expected:

```shell
mail> message "Forecast for tomorrow" \
      --entrypoint supervisor
```

Errors raised by `argparse` are caught and reported without exiting the loop, letting you adjust the command and retry. Blank lines are ignored, and `Ctrl+C` returns you to the prompt without killing the process.

### Streaming inside the REPL
`message-stream` mirrors the behaviour of `MAILClient.post_message_stream`. When the server emits events, each `ServerSentEvent` object is printed in arrival order. This is particularly useful when you want to monitor `task_complete` notifications or inspect intermediate `new_message` / `action_call` events without leaving the terminal.

### Working with Tasks and Breakpoint Resumes

- Both messaging commands accept `--task-id`. Provide it to resume an existing task; omit it to let the server allocate one for a brand-new task.
- To continue a task that paused on a breakpoint tool call, add the following flags:

  ```shell
  mail> message-stream "Continuing after breakpoint" \
        --task-id weather-123 \
        --resume-from breakpoint_tool_call \
        --kwargs '{"breakpoint_tool_call_result": "{\"call_id\":\"bp-1\",\"content\":\"Forecast: sunny\"}"}'
  ```

- The `--kwargs` payload must be valid JSON. For breakpoint resumes the runtime only requires `breakpoint_tool_call_result`; supply a JSON-encoded string that mirrors the tool outputs you received. Provide either a single object (`{"content": "..."}`) or a list of objects (`[{"call_id": "...", "content": "..."}]`) when several breakpoint tools paused in parallel.
- Upon resuming, the runtime reloads any stashed queue entries for the task so the agents pick up exactly where they paused.
- For manual follow-ups, use `--resume-from user_response` to inject a new user message into the same task without losing queued events:

  ```shell
  mail> message "Add a final summary" \
        --task-id weather-123 \
        --resume-from user_response
  ```

### `mail ping`

Check if a MAIL server is reachable and display its health status.

```shell
uv run mail ping http://localhost:8000
```

- The command calls `GET /health` on the target server and reports the swarm name and status.
- Use `--timeout` to override the default 5-second timeout.
- Supports `swarm://` URLs (see below), which are automatically converted to HTTPS.

```shell
# With custom timeout
uv run mail ping http://localhost:8000 --timeout 10

# Using swarm:// URL
uv run mail ping "swarm://connect?server=example.com"
```

On success, you'll see output like:
```
✓ my-swarm is healthy
```

On failure:
```
✗ Cannot connect to http://localhost:8000
```

### `mail db-init`

Initialize PostgreSQL database tables for agent history and task persistence.

```shell
uv run mail db-init
```

- Requires the `DATABASE_URL` environment variable to be set.
- Creates four tables: `agent_histories`, `tasks`, `task_events`, `task_responses`.
- Safe to run multiple times (uses `CREATE TABLE IF NOT EXISTS`).
- See [database.md](./database.md) for schema details and setup instructions.

### `mail register`

Register the MAIL client as the operating system handler for `swarm://` URLs.

```shell
uv run mail register
```

This enables clicking `swarm://` links in browsers or other applications to automatically open the MAIL client.

**Platform support:**

- **Linux**: Creates a `.desktop` file and registers via `xdg-mime`. Fully automated.
- **macOS**: Prints `Info.plist` configuration for app bundling (manual setup required).
- **Windows**: Prints PowerShell commands for registry modification (requires Administrator).

### `swarm://` URL Scheme

The CLI supports `swarm://` URLs for connecting to MAIL servers. This provides a convenient way to share connection details.

**Supported formats:**
```
swarm://connect?server=<hostname>&token=<api_key>
swarm://invite?server=<hostname>&token=<api_key>
```

Both `mail client` and `mail ping` accept these URLs:

```shell
# Connect to a server using swarm:// URL
uv run mail client "swarm://connect?server=example.com&token=my-api-key"

# Ping a server using swarm:// URL
uv run mail ping "swarm://connect?server=example.com"
```

The URL is automatically converted to `https://<server>`. The token (if provided) is used as the API key for `mail client`; `mail ping` ignores the token because `/health` is public.

## Tips
- Use the same environment variables you would for the Python client. The CLI simply wraps `MAILClient` and forwards `--api-key`, `--timeout`, and `--verbose` into `ClientConfig`.
- Combine with `uv run` for isolated environments, e.g. `uv run mail client …`.
- Logging inherits the standard logging configuration. Setting `MAIL_LOG_LEVEL=DEBUG` will surface detailed request/response traces while you use the REPL.

### OpenAI Responses from the REPL
- Ensure the server was started with `--debug`; the `/responses` endpoint is hidden otherwise.
- Supply `INPUT` and `TOOLS` as JSON strings. A minimal request looks like:

  ```shell
  mail> responses '[{"role":"user","content":"Summarise the plan"}]' '[]' 
  ```

- Provide additional OpenAI-compatible fields through the optional flags (for example `--instructions "System prompt"` or `--previous-response-id ...`). The command forwards the parsed JSON directly to the HTTP API.

For deeper programmatic examples refer to [docs/client.md](./client.md).
