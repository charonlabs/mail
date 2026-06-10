# MAIL Standard Library: HTTP Utilities

**Module**: `mail.stdlib.http`

These actions wrap `aiohttp.ClientSession` to provide simple HTTP verbs that agents can compose inside workflows. Each action returns the response body as text on success and an error string prefixed with `"Error:"` on failure. Headers and payloads are passed through without mutation.

> Tip: Install these tools by listing their import strings inside a swarm’s `action_imports`, then grant agents access by name (for example, `"actions": ["http_get"]`).

## Shared payload fields

Every action accepts a JSON object with at least a `url`. Additional fields vary per verb:

- `url` *(string, required)* – Absolute URL to contact.
- `headers` *(object, required for POST/PUT, optional otherwise)* – Key/value pairs forwarded as HTTP headers.
- `body` *(object, required for POST/PUT/PATCH)* – JSON body sent as the request payload.

## Action reference

| Action | Import string | Required fields | Notes |
| --- | --- | --- | --- |
| `http_get` | `python::mail.stdlib.http.actions:http_get` | `url` | Issues a GET and returns `response.text()`. |
| `http_post` | `python::mail.stdlib.http.actions:http_post` | `url`, `headers`, `body` | Sends a JSON POST (errors if `headers` is omitted). |
| `http_put` | `python::mail.stdlib.http.actions:http_put` | `url`, `headers`, `body` | Performs a JSON PUT request (errors if `headers` is omitted). |
| `http_delete` | `python::mail.stdlib.http.actions:http_delete` | `url` | Executes an HTTP DELETE. |
| `http_patch` | `python::mail.stdlib.http.actions:http_patch` | `url`, `body` | Applies a JSON PATCH payload. |
| `http_head` | `python::mail.stdlib.http.actions:http_head` | `url` | Runs a HEAD request and returns the (often empty) response body. |
| `http_options` | `python::mail.stdlib.http.actions:http_options` | `url` | Calls OPTIONS to inspect allowed methods. |

### Usage considerations

- Responses are not parsed—agents can parse JSON downstream if needed.
- Network access must be permitted from the MAIL runtime; these helpers do not bypass proxy restrictions.
- For APIs that require authentication, supply the appropriate `Authorization` header via the `headers` object.
- Errors (connection failures, HTTP exceptions) bubble up as plain strings so agents can decide how to retry or escalate.
