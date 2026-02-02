# MAIL Standard Library

The MAIL reference runtime ships a small but growing set of reusable actions under `mail.stdlib`. These helpers are implemented with the `@mail.action` decorator, so each export is already a fully validated `MAILAction`. You can attach them to agents by adding their names to the agent template, or—more commonly—by listing their import strings inside the swarm-level `action_imports` array so they are automatically wired when a swarm template is loaded.

- For inter-swarm utilities (health checks, registry discovery), see [interswarm.md](./interswarm.md).
- For filesystem helpers (read/write/list), see [fs.md](./fs.md).
- For HTTP client helpers (GET/POST/etc.), see [http.md](./http.md).
- For Model Context Protocol (MCP) helpers that wrap `fastmcp.Client`, see [mcp.md](./mcp.md).

To use one of these actions from configuration:

```json
{
  "name": "example",
  "version": "1.3.2",
  "entrypoint": "supervisor",
  "agents": [...],
  "actions": [],
  "action_imports": [
    "python::mail.stdlib.interswarm.actions:ping_swarm",
    "python::mail.stdlib.mcp.actions:mcp_list_tools"
  ]
}
```

Each import resolves to a `MAILAction` instance. Agents can reference the action by name (for example, `"actions": ["ping_swarm"]`) without redefining its schema or implementation. The sections that follow document every stdlib action, its payload schema, return contract, and any runtime considerations.
