# Configuration

This page describes environment variables and the `swarms.json` file that configures a MAIL deployment.

Environment variables
- `LITELLM_PROXY_API_BASE`: Base URL for your LiteLLM-compatible proxy used by agents
- `AUTH_ENDPOINT`: URL for login endpoint used by the server (Bearer API key -> temporary token)
- `TOKEN_INFO_ENDPOINT`: URL for token info endpoint (Bearer temporary token -> {role,id,api_key})
- `SWARM_NAME`: Name of this swarm instance (default: `example-no-proxy`)
- `BASE_URL`: Base URL for this server (default: `http://localhost:8000`)
- `SWARM_REGISTRY_FILE`: Path used by the server to persist non-volatile registry entries (default: `registries/example.json`)
- Optional provider keys consumed by your proxy (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

swarms.json
- Defines the persistent swarm template loaded on server startup
- Sets the entrypoint agent and the set of available agents and actions
- Agents are built via factories referenced by import path strings; prompts and actions are configured per agent

Minimal example
```
[
  {
    "name": "example",
    "version": "1.0.0",
    "entrypoint": "supervisor",
    "agents": [
      {
        "name": "supervisor",
        "factory": "mail.factories.supervisor:supervisor_factory",
        "llm": "openai/o3-mini",
        "system": "mail.examples.supervisor.prompts:SYSPROMPT",
        "comm_targets": ["weather", "math"],
        "agent_params": {}
      },
      {
        "name": "weather",
        "factory": "mail.examples.weather_dummy.agent:factory_weather_dummy",
        "llm": "openai/o3-mini",
        "system": "mail.examples.weather_dummy.prompts:SYSPROMPT",
        "comm_targets": ["supervisor", "math"],
        "agent_params": {
          "actions": [
            {
              "name": "get_weather_forecast",
              "description": "Get the weather forecast",
              "parameters": {"type": "object", "properties": {"location": {"type": "string"}}},
              "function": "mail.examples.weather_dummy.actions:get_weather_forecast"
            }
          ]
        }
      },
      {
        "name": "math",
        "factory": "mail.examples.math_dummy.agent:factory_math_dummy",
        "llm": "openai/o3-mini",
        "system": "mail.examples.math_dummy.prompts:SYSPROMPT",
        "comm_targets": ["supervisor", "weather"],
        "agent_params": {}
      }
    ]
  }
]
```

Notes
- `comm_targets` must reference existing agents by name, or interswarm addresses if interswarm is enabled
- Exactly one or more entrypoint-capable agents must be present; the top-level `entrypoint` names which one to use by default
- Actions defined at the agent level become available to that agent via tools; see agents-and-tools.md

