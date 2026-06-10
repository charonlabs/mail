# MAIL Standard Library: Model Context Protocol (MCP) Utilities

**Module**: `mail.stdlib.mcp`

These actions wrap the [`fastmcp`](https://github.com/jlowin/fastmcp) client so agents can inspect and interact with remote Model Context Protocol servers. Every action expects a valid `server_url` that points to an MCP endpoint reachable from the MAIL runtime. Return values are plain strings—the underlying MCP responses are converted with `str(...)` to keep tool outputs concise.

## Action reference

| Action | Import string | Required fields | Description |
| --- | --- | --- | --- |
| `mcp_ping` | `python::mail.stdlib.mcp:mcp_ping` | `server_url: str` | Performs a health-style `ping()` against the MCP server and returns the response string. |
| `mcp_list_tools` | `python::mail.stdlib.mcp:mcp_list_tools` | `server_url: str` | Calls `list_tools()` and returns the server-provided listing. |
| `mcp_list_prompts` | `python::mail.stdlib.mcp:mcp_list_prompts` | `server_url: str` | Enumerates available prompts via `list_prompts()`. |
| `mcp_get_prompt` | `python::mail.stdlib.mcp:mcp_get_prompt` | `server_url: str`, `prompt_name: str` | Fetches a specific prompt definition. |
| `mcp_list_resources` | `python::mail.stdlib.mcp:mcp_list_resources` | `server_url: str` | Returns the resource catalogue from `list_resources()`. |
| `mcp_read_resource` | `python::mail.stdlib.mcp:mcp_read_resource` | `server_url: str`, `resource_uri: str` | Retrieves a resource’s contents. |
| `mcp_call_tool` | `python::mail.stdlib.mcp:mcp_call_tool` | `server_url: str`, `tool_name: str`, `tool_input: dict` | Invokes a named tool with the provided input payload. |

### Payload schemas

All MCP actions share a top-level JSON Schema object with the properties listed below. Required keys vary per action (see the table above).

- `server_url`: string — Base URL of the MCP server.
- `tool_name`: string — Required only for `mcp_call_tool`.
- `tool_input`: object — Arbitrary tool input passed through to the MCP server, required for `mcp_call_tool`.
- `prompt_name`: string — Required for `mcp_get_prompt`.
- `resource_uri`: string — Required for `mcp_read_resource`.

Because each helper is already decorated with `@mail.action`, the MAIL runtime validates the payload before executing RPCs. Errors are caught and returned as strings prefixed with `"Error:"`, so agents can surface them without raising exceptions.

### Usage tips

- When defining swarms, add the desired import paths to the `action_imports` list and then reference the action names from agent templates. Example:

  ```json
  {
    "action_imports": [
      "python::mail.stdlib.mcp.actions:mcp_list_tools",
      "python::mail.stdlib.mcp.actions:mcp_call_tool"
    ],
    "agents": [
      {
        "name": "supervisor",
        "actions": ["mcp_list_tools", "mcp_call_tool"],
        "agent_params": {}
      }
    ]
  }
  ```

- The stdlib relies on `fastmcp.Client` and therefore requires event-loop friendly environments; no additional configuration is needed beyond network reachability to the MCP endpoint.

- Responses can be large (for example, reading resources). You can post-process inside the agent if you need structured parsing.
