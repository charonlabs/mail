# HTTP API

Status: draft

This is a navigational reference to the MAIL server's HTTP surface. The
authoritative contract — request bodies, response schemas, parameters, and status
codes — is the generated [`spec/openapi.yaml`](../../spec/openapi.yaml), also
served interactively at `/docs` (Swagger UI) and `/openapi.json` on a running
server. This page lists every route, its authentication requirement, and its
response model so you can find the right endpoint; follow the OpenAPI schema for
exact field-level detail. Route handlers live in
[`src/mail/server/src/mail_server/routers/`](../../src/mail/server/src/mail_server/routers).

## Authentication

Every authenticated request carries a bearer access token in the
`Authorization: Bearer <token>` header. Obtain one from `POST /auth/token` (see
[Authenticate a User-Agent](../howtos/authenticate-user-agent.md)). Endpoints
enforce one of four access levels:

| Level | Meaning |
| --- | --- |
| none | Unauthenticated. |
| user-agent | Any authenticated user-agent (agent, user, admin, daemon). |
| daemon | A daemon bearer token carrying the endpoint's required OAuth scope. |
| HTTP signature | RFC 9421 signature verified with the origin's HTTPS-discovered Ed25519 key; no local bearer token. |
| admin | An admin bearer token. |

## Response envelope

Most responses wrap their payload in a named field (`entry`, `entries`,
`message`, `swarm`, `mail_list`, …) alongside a `metadata` object; single-message
box reads nest the message under an `entry`. Field shapes are in
[Data Models](data-models.md).

> **Memory-backend gaps.** A few endpoints are implemented only on the SQLite
> backend; on the memory backend they raise `NotImplementedError`:
> `DELETE /inbox/{message_id}`, `DELETE /drafts/{draft_id}`,
> `DELETE /trash/{message_id}`, `POST /trash/clear`,
> and `PATCH /admin/webhooks/{webhook_id}`. See
> [Storage Backends](storage-backends.md#current-limitations).

## Root and health

| Method | Path | Auth | Response model |
| --- | --- | --- | --- |
| GET | `/` | none | `RootGetResponse` (protocol name, version, uptime) |
| GET | `/health` | none | `HealthGetResponse` (`status: "ok"`) |

## Authentication endpoints (`/auth`)

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/auth/token` | none | OAuth2 password grant. Daemons request an assigned space-delimited `scope`; the response and JWT carry the grant. Interactive principals alone receive a `refresh_token`. |
| POST | `/auth/refresh` | refresh token | Rotates the refresh token (cookie or request body). |
| POST | `/auth/logout` | refresh token | Idempotent; revokes the refresh family. |
| GET | `/auth/whoami` | user-agent | Returns the caller's `MAILUserAgent`. |
| POST | `/auth/password/reset` | user-agent | Revokes all refresh families on success. |

See [Security Model](../explanations/security-model.md) for the refresh-token
design.

## Swarms (`/swarms`)

| Method | Path | Auth | Response model |
| --- | --- | --- | --- |
| GET | `/swarms` | user-agent | `SwarmsGetResponse` |
| GET | `/swarms/{swarm_name}` | user-agent | `SwarmGetResponse` |
| GET | `/swarms/{swarm_name}/health` | user-agent | `SwarmHealthGetResponse` |

## Message boxes

Box GET-collection endpoints accept the `BoxFilterParams` query params: `limit`
(1–100, default 20), `offset` (default 0), `sort_by` (`entered_at` default, or
`sent_at`), and `order` (`desc` default, or `asc`). `GET /drafts` rejects
`sort_by=sent_at` with `422` (a draft has no send time).

### Inbox (`/inbox`)

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/inbox` | user-agent | List summaries (per-owner `is_read`). |
| GET | `/inbox/{message_id}` | user-agent | Full message; marks it read. |
| DELETE | `/inbox/{message_id}` | user-agent | Moves the message to trash. |

### Outbox (`/outbox`)

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/outbox` | user-agent |
| GET | `/outbox/{message_id}` | user-agent |

### Drafts (`/drafts`)

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/drafts` | user-agent | Rejects `sort_by=sent_at` (`422`). |
| POST | `/drafts` | user-agent | Create a draft (`subject`, `body`, optional `reply_to`, `tags`). |
| GET | `/drafts/{draft_id}` | user-agent | |
| PATCH | `/drafts/{draft_id}` | user-agent | Partial update; omitted fields unchanged. |
| DELETE | `/drafts/{draft_id}` | user-agent | |
| POST | `/drafts/{draft_id}/send` | user-agent | Bind `recipients` and send. Daemons need `deliver:local` for local-only sends or `deliver:federate` when any recipient is remote. Remote sends return `503` while federation is disabled. |

### Trash (`/trash`)

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/trash` | user-agent |
| GET | `/trash/{message_id}` | user-agent |
| DELETE | `/trash/{message_id}` | user-agent |
| POST | `/trash/clear` | user-agent |

## Daemon endpoints (`/daemon`)

Used by delivery daemons; see [Delivery Model](../explanations/delivery-model.md).

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/daemon/message-buffer/clear` | daemon + `deliver:local` | Drain the pending-delivery buffer. |
| POST | `/daemon/deliver/local` | daemon + `deliver:local` | Deliver messages between user-agents on this server. |
| POST | `/daemon/deliver/remote/v1` | HTTP signature | Accept and durably queue one Federation v1 envelope. |
| POST | `/daemon/deliver/remote` | none | Removed unsigned endpoint; always returns `410`. |

Federation-enabled servers also expose `GET /.well-known/mail-federation`
without bearer authentication. Disabled servers return `404` from both public
federation routes.

Federation ingress caps the raw body before parsing, then verifies signature
headers, the discovered origin key, signature/digest, envelope and host
invariants, five-minute freshness, 24-hour replay state, policy, and recipient
existence. `202` means the inner message and local queue entry committed;
duplicate envelope IDs return `409`. Authentication failures return `401`,
verified policy/host denials `403`, envelope violations `400`, oversized bodies
`413`, and transient local pressure `429` or `503`, with machine-readable error
codes. The removed unsigned route always returns `410`.

Reverse proxies must preserve the externally observed HTTPS target URI,
authority, raw body bytes, and all signature headers. See
[Enable and Operate Federation](../howtos/enable-federation.md#4-preserve-signed-request-inputs-at-the-proxy).

## Admin endpoints (`/admin`)

All require admin. Address path params use the **local** form (`agent@swarm`,
`name@swarm`); user/daemon use their id / worker name.

| Resource | Routes |
| --- | --- |
| Agents | `GET|POST /admin/agents`, `GET|DELETE /admin/agents/{local_address}` |
| Daemons | `GET|POST /admin/daemons`, `GET|DELETE /admin/daemons/{worker_name}` |
| Users | `GET|POST /admin/users`, `GET|DELETE /admin/users/{user_id}` |
| Swarms | `POST /admin/swarms`, `DELETE /admin/swarms/{swarm_name}` |
| Webhooks | `GET|POST /admin/webhooks`, `GET|PATCH|DELETE /admin/webhooks/{webhook_id}` |

## Mailing list endpoints

See [Mailing Lists](../explanations/mailing-lists.md) and
[Manage Mailing Lists](../howtos/manage-mailing-lists.md). List path params use
the **local** `name@swarm` form; the server reconstructs the canonical
`list:name@swarm@host`.

### Admin lists (`/admin/lists`, admin)

| Method | Path |
| --- | --- |
| GET | `/admin/lists` |
| POST | `/admin/lists` |
| GET / PATCH / DELETE | `/admin/lists/{local_address}` |
| POST | `/admin/lists/{local_address}/members` |
| DELETE | `/admin/lists/{local_address}/members/{member_address}` |

### Public lists (`/lists`, user-agent)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/lists` | Filtered to `visibility=public`. |
| GET | `/lists/{local_address}` | `404` if not public. |
| POST | `/lists/{local_address}/subscribe` | `501` unless `join_policy=open`. |
| POST | `/lists/{local_address}/unsubscribe` | |

## Common status codes

| Code | Meaning in MAIL |
| --- | --- |
| `401 Unauthorized` | Missing, malformed, or expired token. |
| `403 Forbidden` | Authenticated but wrong role (e.g. non-admin on `/admin`). |
| `404 Not Found` | Unknown resource (or a non-public list on `/lists`). |
| `422 Unprocessable Entity` | Request/query validation failed; `detail` explains what. |
| `501 Not Implemented` | Reserved-but-unsupported behavior (non-`open` list policies). |

## Maintenance notes

Prefer the generated OpenAPI details for schemas and parameters; keep this page
focused on navigation, auth levels, and implementation notes. When routes change,
regenerate `spec/openapi.yaml` ([Regenerate API Artifacts](../howtos/regenerate-api-artifacts.md))
and update the tables here.
