# Configuration

This page describes environment variables and the `swarms.json` file that configures a MAIL deployment.

## Environment variables
- `LITELLM_PROXY_API_BASE`: Base URL for your LiteLLM-compatible proxy used by agents
- `AUTH_ENDPOINT`: URL for login endpoint used by the server (Bearer API key -> temporary token)
- `TOKEN_INFO_ENDPOINT`: URL for token info endpoint (Bearer temporary token -> {role,id,api_key})
- `SWARM_NAME`: Name of this swarm instance (default: `example-no-proxy`)
- `BASE_URL`: Base URL for this server (default: `http://localhost:8000`)
- `SWARM_REGISTRY_FILE`: Path used by the server to persist non-volatile registry entries (default: `registries/example.json`)
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
        "version": "1.0.1",
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
- The helpers in `mail.json.utils` can be used to validate and load `swarms.json` prior to instantiating templates

### Prefixed string references
- `python::package.module:attribute` strings resolve to Python objects at load time; use this for reusing constants such as prompts or tool factories
- `url::https://example.com/prompt.json` strings are fetched with `httpx` and replaced by the response JSON encoded as a string
- Nested dictionaries and lists inside `agent_params` (and other configuration blocks) are resolved recursively, so you can mix plain literals with both prefix formats
- `url::` fetch failures return the original URL unless you set `raise_on_error` when calling `mail.utils.parsing.read_url_string`, which converts errors into descriptive `RuntimeError`s
