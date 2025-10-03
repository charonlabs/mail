# Configuration

This page describes the configuration surfaces for a MAIL deployment: the project-level `mail.toml`, relevant environment variables, and the `swarms.json` swarm template.

## mail.toml

`mail.toml` provides defaults for both the server and client reference implementations. The CLI, API, and configuration models read from this file the first time configuration is needed.

```toml
[server]
port = 8000
host = "0.0.0.0"
reload = false

[server.swarm]
name = "example-no-proxy"
source = "swarms.json"
registry = "registries/example-no-proxy.json"

[client]
timeout = 3600.0
```

- The `[server]` table controls how Uvicorn listens (`port`, `host`, `reload`).
- The `[server.swarm]` table specifies the persistent swarm template (`source`), the registry persistence file (`registry`), and the runtime swarm name (`name`).
- The `[client]` table currently exposes a single `timeout` option (seconds). It feeds `ClientConfig` which in turn sets the default timeout for `MAILClient` and the CLI REPL.
- Instantiating `ServerConfig()` or `ClientConfig()` with no arguments uses these values as defaults; if a key is missing or the file is absent, the literal defaults above are applied.
- The CLI command `mail server` accepts `--port`, `--host`, `--reload`, `--swarm-name`, `--swarm-source`, and `--swarm-registry`. Provided flags override the file-driven defaults, while omitted flags continue to use `mail.toml` values.
- The CLI command `mail client` honors `timeout` from `[client]` and allows `--timeout` to override it per invocation.
- Set `MAIL_CONFIG_PATH` to point at an alternate `mail.toml` (for example per environment). `mail server --config /path/to/mail.toml` temporarily overrides this variable for the lifetime of the command.

## Environment variables
- `LITELLM_PROXY_API_BASE`: Base URL for your LiteLLM-compatible proxy used by agents
- `AUTH_ENDPOINT`: URL for login endpoint used by the server (Bearer API key -> temporary token)
- `TOKEN_INFO_ENDPOINT`: URL for token info endpoint (Bearer temporary token -> {role,id,api_key})
- `SWARM_NAME`: Name of this swarm instance. Overrides the value calculated from `mail.toml`.
- `BASE_URL`: Base URL for this server. Overrides the derived value (defaults to `http://localhost:<port>`).
- `SWARM_REGISTRY_FILE`: Path used by the server to persist non-volatile registry entries. Overrides the `mail.toml` default.
- Optional provider keys consumed by your proxy (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

## swarms.json
- Defines the persistent swarm template loaded on server startup
- Sets the entrypoint agent and the set of available agents and actions
- Agents are built via factories referenced by import path strings; prompts and actions are configured per agent

### Minimal example
```json
[
    {
        "name": "example",
        "version": "1.1.0",
        "entrypoint": "supervisor",
        "enable_interswarm": true,
        "agents": [
            {
                "name": "supervisor",
                "factory": "mail.factories.supervisor:supervisor_factory",
                "comm_targets": ["weather", "math"],
                "enable_entrypoint": true,
                "can_complete_tasks": true,
                "agent_params": {
                    "llm": "openai/gpt-5-mini",
                    "system": "mail.examples.supervisor.prompts:SYSPROMPT"
                }
            },
            {
                "name": "weather",
                "factory": "mail.examples.weather_dummy.agent:factory_weather_dummy",
                "comm_targets": ["supervisor", "math"],
                "actions": ["get_weather_forecast"],
                "agent_params": {
                    "llm": "openai/gpt-5-mini",
                    "system": "mail.examples.weather_dummy.prompts:SYSPROMPT"
                }
            },
            {
                "name": "math",
                "factory": "mail.examples.math_dummy.agent:factory_math_dummy",
                "comm_targets": ["supervisor", "weather"],
                "agent_params": {
                    "llm": "openai/gpt-5-mini",
                    "system": "mail.examples.math_dummy.prompts:SYSPROMPT"
                }
            }
        ],
        "actions": [
            {
                "name": "get_weather_forecast",
                "description": "Get the weather forecast for a given location",
                "parameters": { 
                    "type": "object",
                    "properties": {
                        "location": { "type": "string", "description": "The location to get the weather forecast for" },
                        "days_ahead": { "type": "integer", "description": "The number of days ahead to get the weather forecast for" },
                        "metric": { "type": "boolean", "description": "Whether to use metric units" }
                    }
                },
                "function": "mail.examples.weather_dummy.actions:get_weather_forecast"
            }
        ]
    }
]
```

### Notes
- `comm_targets` must reference existing agents by name, or interswarm addresses if interswarm is enabled
- Exactly one or more entrypoint-capable agents must be present; the top-level `entrypoint` names which one to use by default
- Actions are declared once at the swarm level and referenced by name in each agent's `actions` list; [see agents-and-tools.md](/docs/agents-and-tools.md)
- `version` is required and should match the MAIL package you are targeting so migrations can gate incompatible swarm definitions
- The helpers in `mail.swarms_json.utils` can be used to validate and load `swarms.json` prior to instantiating templates

### Prefixed string references
- `python::package.module:attribute` strings resolve to Python objects at load time; use this for reusing constants such as prompts or tool factories
- `url::https://example.com/prompt.json` strings are fetched with `httpx` and replaced by the response JSON encoded as a string
- Nested dictionaries and lists inside `agent_params` (and other configuration blocks) are resolved recursively, so you can mix plain literals with both prefix formats
- `url::` fetch failures return the original URL unless you set `raise_on_error` when calling `mail.utils.parsing.read_url_string`, which converts errors into descriptive `RuntimeError`s
