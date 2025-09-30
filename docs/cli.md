# MAIL Command-Line Interface

The reference implementation ships with a convenience CLI that lets you run the FastAPI server and talk to it interactively from the same entry point.
Both commands are exposed via the console script `mail`, which is installed when you install this package (`uv sync` or `pip install -e .`).

## Commands

```shell
mail server   # run the FastAPI reference server
mail client   # launch the interactive MAIL client REPL
```

The top-level parser accepts the same flags regardless of how you invoke it, for example `python -m mail.cli …` or `uv run mail …`.

### `mail server`
- Configuration defaults are read from `mail.toml` (see
  [configuration.md](./configuration.md)). Flags such as `--host`, `--port`, `--reload`, `--swarm-name`, `--swarm-source`, and `--swarm-registry` only override the values you provide.
- Use `--config /path/to/mail.toml` to point at a different   configuration file for a single run. The environment variable `MAIL_CONFIG_PATH` acts as the persistent override if you prefer exporting it once.
- Environment variables such as `AUTH_ENDPOINT`, `TOKEN_INFO_ENDPOINT`, and `LITELLM_PROXY_API_BASE` remain required; the CLI does not provide defaults for them.
- Example:

  ```bash
  uv run mail server --host 0.0.0.0 --port 8000 --reload
  ```

### `mail client`
Launching `mail client` starts the interactive REPL.

- The default timeout comes from the `[client]` table in `mail.toml`; override
  it per invocation with `--timeout`.
- The `--config` flag is shared with `mail server`, allowing you to point both
  commands at the same config file if you keep multiple TOML profiles.

```shell
uv run mail client --url http://localhost:8000 --api-key $USER_TOKEN
```

Once inside you will see the prompt `mail>`. The REPL accepts any of the subcommands documented in [docs/client.md](./client.md), plus a few helper commands:

| Command | Description |
| --- | --- |
| `help` or `?` | Print CLI usage information without exiting the loop. |
| `exit` / `quit` | Leave the REPL. |
| `get-health` | Invoke `GET /health` and print the JSON body. |
| `post-message --message "…" [--entrypoint …] [--show-events]` | Submit a message and print the structured response. |
| `post-message-stream --message "…"` | Stream SSE events; each event is printed as it arrives. |
| `get-swarms`, `register-swarm`, `dump-swarm` | Manage the swarm registry. |
| `send-interswarm-message` | Send interswarm traffic by target agent. |
| `load-swarm-from-json` | Submit a JSON payload to `POST /swarms/load`. |

The REPL uses `shlex.split`, so quoting works as expected:

```shell
mail> post-message --message "Forecast for tomorrow" --entrypoint supervisor
```

Errors raised by `argparse` are caught and reported without exiting the loop,
letting you adjust the command and retry. Blank lines are ignored, and
`Ctrl+C` returns you to the prompt without killing the process.

### Streaming inside the REPL
`post-message-stream` mirrors the behaviour of `MAILClient.post_message_stream`.
When the server emits events, each `ServerSentEvent` object is printed in
arrival order. This is particularly useful when you want to monitor `task_complete`
notifications or inspect intermediate `new_message` / `action_call` events
without leaving the terminal.

## Tips
- Use the same environment variables you would for the Python client. The CLI simply wraps `MAILClient` and forwards `--url`, `--api-key`, and `--timeout`.
- Combine with `uv run` for isolated environments, e.g. `uv run mail client …`.
- Logging inherits the standard logging configuration. Setting `MAIL_LOG_LEVEL=DEBUG` will surface detailed request/response traces while you use the REPL.

For deeper programmatic examples refer to [docs/client.md](./client.md).
