# MAIL Standard Library: Interswarm Utilities

**Module**: `mail.stdlib.interswarm`

These helpers let supervisors inspect or discover remote swarms over HTTP. All three actions share the same payload schema:

```json
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "Base URL of the remote MAIL swarm (e.g., https://demo.example.com)"
    }
  },
  "required": ["url"]
}
```

## `ping_swarm`
- **Import**: `python::mail.stdlib.interswarm:ping_swarm`
- **Description**: Issues a `GET /` request to the target swarm. Returns `"pong"` when the endpoint responds with a valid MAIL root payload; otherwise surfaces a prefixed error string.
- **Typical use**: Attach to a supervisor so it can validate multi-swarm connectivity before dispatching interswarm requests.

## `get_swarm_health`
- **Import**: `python::mail.stdlib.interswarm:get_swarm_health`
- **Description**: Calls `GET /health` and returns the status string when the response matches the MAIL health contract. Errors are returned as readable strings.
- **Typical use**: Combine with dashboards or periodic health probes to monitor remote swarms.

## `get_swarm_registry`
- **Import**: `python::mail.stdlib.interswarm:get_swarm_registry`
- **Description**: Fetches `GET /swarms` from the remote swarm, validates the payload, and returns a newline-delimited list in the format `<swarm_name>@<base_url>`. Errors produce prefixed strings.
- **Typical use**: Allow supervisors to bulk import or audit registered swarms without leaving the MAIL runtime.

All actions will raise structured error strings like `"Error: <details>"` if validation fails or the HTTP call errors; the runtime treats these as regular tool responses. Wrap them via `action_imports` to avoid duplicating schemas in `swarms.json`.
