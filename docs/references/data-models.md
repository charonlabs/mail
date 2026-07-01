# Data Models

Status: draft

The MAIL protocol types are Pydantic models in the `mail-swarms-protocol`
package: domain models under
[`core/`](../../src/mail/protocol/src/mail_protocol/core) and wire
request/response models under
[`network/`](../../src/mail/protocol/src/mail_protocol/network). This page
documents the domain models field-by-field and summarizes the wire models; for
the exact HTTP request/response schemas see
[`spec/openapi.yaml`](../../spec/openapi.yaml) and [HTTP API](http-api.md).

## Conventions

- **Validators.** Field rules are `AfterValidator` functions from
  [`core/validators.py`](../../src/mail/protocol/src/mail_protocol/core/validators.py);
  the tables name the validator. See [Validators](#validators) for what each
  enforces.
- **`metadata`.** Most models carry a `metadata: dict[str, Any]` for
  implementer-defined data (SPEC §7.7). Put custom data there, not at the top
  level.
- **`.summarize()`.** Full models have a `summarize()` returning a `*Summary`
  variant (smaller, `body_size` instead of `body`) used in list responses.
- **`*InBackend`.** Storage-only variants add server-assigned fields (ids,
  timestamps, password hashes) and never cross the wire as input.

## User-agents and addresses

Four concrete types discriminated on `ua_type`, each with a `get_address()`.
Defined in
[`core/user_agents.py`](../../src/mail/protocol/src/mail_protocol/core/user_agents.py).
See [Addressing Model](../explanations/addressing-model.md) for the address
grammar.

| Model | `ua_type` | Address form | Identifying field (validator) |
| --- | --- | --- | --- |
| `MAILAgent` | `"agent"` | `name@swarm@host` | `name` (`validate_agent_name`), `swarm`, `host` |
| `MAILUser` | `"user"` | `user:user_id@host` | `user_id` (`validate_user_name`), `host` |
| `MAILAdmin` | `"admin"` | `admin:admin_id@host` | `admin_id` (`validate_user_name`), `host` |
| `MAILDaemon` | `"daemon"` | `daemon:worker_name@host` | `worker_name` (`validate_daemon_worker_name`), `host` |

- **`MAILUserAgent`** — wrapper with `user_agent: Union[...]` as a
  `Field(discriminator="ua_type")`. This is the shape returned by
  `GET /auth/whoami` (double-nested: `user_agent.user_agent`).
- **`MAILUserAgentInBackend`** — adds `hashed_password: str`.

## Messages

[`core/messages.py`](../../src/mail/protocol/src/mail_protocol/core/messages.py).
The message contract is SPEC §7.

### `MAILMessage`

| Field | Type | Default | Validator |
| --- | --- | --- | --- |
| `mail_version` | `Literal["2.0"]` | required | — |
| `message_id` | `str` | required | `validate_uuid` |
| `reply_to` | `str \| None` | `None` | `validate_uuid` |
| `sender` | `str` | required | `validate_mail_address` |
| `recipients` | `list[str]` | required | `validate_message_recipients` (≥1) |
| `subject` | `str` | required | `validate_message_subject` |
| `body` | `str` | required | `validate_message_body` |
| `tags` | `list[str]` | required | `validate_message_tags` |
| `sent_at` | `datetime` | required | — |
| `metadata` | `dict[str, Any]` | required | — |

**`MAILMessageSummary`** drops `mail_version`/`reply_to`/`body`/`tags`/`metadata`
and carries `body_size: int` instead of `body`.

## Drafts

[`core/drafts.py`](../../src/mail/protocol/src/mail_protocol/core/drafts.py). A
draft has no recipients — they are bound at send time. `reply_to`/`tags` carry
forward onto the sent message.

### `MAILDraft`

| Field | Type | Default | Validator |
| --- | --- | --- | --- |
| `draft_id` | `str` | required | `validate_uuid` |
| `subject` | `str` | required | `validate_message_subject` |
| `body` | `str` | required | `validate_message_body` |
| `created_at` | `datetime` | required | — |
| `updated_at` | `datetime \| None` | `None` | — |
| `reply_to` | `str \| None` | `None` | `validate_uuid` |
| `tags` | `list[str]` | `[]` | `validate_message_tags` |

**`MAILDraftsEntry`** wraps a `MAILDraft` with `sent_at: datetime | None` and
`sent_by: str | None`. **`MAILDraftsEntrySummary`** mirrors it with `body_size`.

## Box entries

Each box wraps a `MAILMessage` with box-specific timestamps; each has a `*Summary`
for list views. Modules:
[inbox](../../src/mail/protocol/src/mail_protocol/core/inbox.py),
[outbox](../../src/mail/protocol/src/mail_protocol/core/outbox.py),
[trash](../../src/mail/protocol/src/mail_protocol/core/trash.py).

| Entry | Wraps | Extra fields |
| --- | --- | --- |
| `MAILInboxEntry` | `MAILMessage` | `received_at`, `delivered_by` |
| `MAILOutboxEntry` | `MAILMessage` | `delivered_at: datetime \| None`, `delivered_by: str \| None` |
| `MAILTrashEntry` | `MAILMessage` | `trashed_at` |

Summary specifics:

- **`MAILInboxEntrySummary`** carries `is_read: bool = False`. Read state is
  per-owner and supplied at list time (not stored on the shared entry); it flips
  to `True` when the message is fetched via `GET /inbox/{message_id}`.
- **`MAILOutboxEntrySummary`** carries nullable `delivered_at` / `delivered_by`
  — `null` means *sent, awaiting delivery* (see
  [Delivery Model](../explanations/delivery-model.md)).

## Swarms

[`core/swarms.py`](../../src/mail/protocol/src/mail_protocol/core/swarms.py).

### `MAILSwarm`

| Field | Type | Validator |
| --- | --- | --- |
| `name` | `str` | `validate_swarm_name` |
| `description` | `str` | `validate_swarm_description` |
| `keywords` | `list[str]` | `validate_swarm_keywords` |
| `agents` | `list[str]` | `validate_agent_names` |
| `metadata` | `dict[str, Any]` | — |

**`MAILSwarmSummary`** replaces `agents`/`metadata` with `num_agents: int`.

## Mailing lists

[`core/lists.py`](../../src/mail/protocol/src/mail_protocol/core/lists.py). See
[Mailing Lists](../explanations/mailing-lists.md) for the model in prose.

### `MAILListPolicy`

| Field | Type | Default |
| --- | --- | --- |
| `visibility` | `Literal["public", "private"]` | `"public"` |
| `join_policy` | `Literal["open", "approval", "admin-only"]` | `"open"` |
| `send_policy` | `Literal["open", "members-only", "admin-only"]` | `"open"` |

The non-default enum variants are reserved: they validate at the protocol layer
but the v1 server rejects them with `501`.

### `MAILList`

| Field | Type | Default | Validator |
| --- | --- | --- | --- |
| `list_type` | `Literal["list"]` | `"list"` | — |
| `name` | `str` | required | `validate_list_name` |
| `swarm` | `str` | required | `validate_swarm_name` |
| `host` | `str` | required | `validate_host` |
| `owner` | `str` | required | `validate_mail_address` |
| `members` | `list[str]` | `[]` | `validate_mail_addresses` |
| `policy` | `MAILListPolicy` | `MAILListPolicy()` | — |
| `metadata` | `dict[str, Any]` | `{}` | — |

**`MAILListInBackend`** adds `list_id` (`validate_uuid`), `created_at`,
`updated_at`. This is the payload shape in all list responses. Address form via
`get_address()`: `list:name@swarm@host`.

## Webhooks

[`core/webhooks.py`](../../src/mail/protocol/src/mail_protocol/core/webhooks.py),
[`network/webhooks.py`](../../src/mail/protocol/src/mail_protocol/network/webhooks.py).
The only event type is `mail.delivered`. See
[Webhook Delivery](../explanations/webhook-delivery.md).

- **`MAILWebhook`** — `webhook_id` (`wh_<uuid>`), `url` (`validate_url`), `events`
  (`validate_webhook_event_types`), `secret`.
- **`MAILMessageInWebhook`** — the message as embedded in an outbound payload. It
  **diverges from `MAILMessage`**: IDs are `msg_`-prefixed, there is a single
  `recipient` (not `recipients`), it adds a `swarm` field, and it omits
  `mail_version`.
- **`WebhookDeliveredPostRequest`** — the JSON body the server POSTs to receiver
  URLs: `event`, `event_id`, `delivered_at`, `message: MAILMessageInWebhook`.
  (This is outbound; it is not an endpoint the server exposes.)

## Auth

[`core/auth.py`](../../src/mail/protocol/src/mail_protocol/core/auth.py).

**`RefreshTokenRecord`** (backend-internal; never on the wire) stores the SHA-256
hash of a refresh token, its `family_id`, `owner_address`, `issued_at`, absolute
`expires_at`, a `revoked` flag, and `rotated_at`. A token is unusable once
`revoked` is true or `rotated_at` is set. See
[Security Model](../explanations/security-model.md).

## Request and response models

The wire envelopes live in
[`network/requests.py`](../../src/mail/protocol/src/mail_protocol/network/requests.py)
and
[`network/responses.py`](../../src/mail/protocol/src/mail_protocol/network/responses.py),
and each maps to an endpoint in [HTTP API](http-api.md) (most docstrings name the
`METHOD /path`). Rather than restate the generated schema, note the recurring
shapes:

- **Responses** wrap a payload field (`entry`, `entries`, `message`, `swarm`,
  `mail_list`, `agent`, …) plus `metadata`. A handful of pure-status responses
  (`RootGetResponse`, `HealthGetResponse`, `SwarmHealthGetResponse`,
  `AuthLogoutPostResponse`, `AuthPasswordResetResponse`) omit `metadata`.
- **Notable request bodies:** `DraftPostRequest` (`subject`, `body`, optional
  `reply_to`, `tags`), `DraftPatchRequest` (all-optional partial update),
  `DraftSendPostRequest` (`recipients`, optional `tags` merged with the draft's),
  `AdminListPostRequest` / `AdminListPatchRequest` (policy-only patch),
  `AdminWebhooksPostRequest` / `AdminWebhooksPatchRequest`, and the admin
  create-agent/daemon/user/swarm bodies.
- **`BoxFilterParams`** — the query params for box GET-collection endpoints:
  `limit` (1–100, default 20), `offset` (default 0), `sort_by`
  (`entered_at`|`sent_at`, default `entered_at`), `order` (`asc`|`desc`, default
  `desc`). It forbids extra params.

## Constants

[`core/constants.py`](../../src/mail/protocol/src/mail_protocol/core/constants.py):

| Constant | Min / Max |
| --- | --- |
| Message subject | 1 / 256 |
| Message body | 1 / 65535 |
| Message tag | 1 / 32 |
| Agent / user / admin / daemon-worker / swarm / swarm-keyword / list name | 1 / 32 |
| Swarm description | 0 / 255 |

`LIST_ADDRESS_PREFIX = "list"`. The protocol version literal `"2.0"` is not a
constant — it is a `Literal` on `MAILMessage.mail_version` and
`RootGetResponse.protocol_version`. The identifier max of 32 matches SPEC §6.

## Validators

Key rules from `core/validators.py`:

| Validator | Enforces |
| --- | --- |
| `validate_uuid` / `validate_uuids` | Value(s) parse as UUIDs. |
| `validate_mail_address` | Full address shape: 3-part `name@swarm@host` (agent) or `list:name@swarm@host`; 2-part `user:id@host` / `admin:id@host` / `daemon:worker@host`. |
| `validate_local_address` | 2-part `agent@swarm` (admin path params). |
| `validate_message_recipients` | ≥1 entry, each a valid address (SPEC §7.3). |
| `validate_message_subject` / `_body` | Length within the constant bounds. |
| `validate_message_tag(s)` | Each tag length 1–32 and a slug. |
| `validate_agent_name` / `validate_user_name` / `validate_swarm_name` / `validate_daemon_worker_name` / `validate_list_name` / `validate_swarm_keyword` | Length 1–31 and a slug. |
| `validate_host` | Valid hostname, IPv4, or IPv6. |
| `validate_url` | `http(s)://` URL (single-label hosts like `localhost` allowed). |
| `validate_webhook_id` / `validate_webhook_message_id` | `wh_<uuid>` / `msg_<uuid>` shapes. |
| `validate_webhook_event_type(s)` | Equals `mail.delivered`. |

The slug rule (`string_is_slug`) is `^[a-z0-9]+(?:-[a-z0-9]+)*$`: lowercase
alphanumerics in hyphen-separated segments — no uppercase, underscores, or
leading/trailing/double hyphens.

## Maintenance notes

Use field tables with type, default/required status, and the validator name; link
to the source class rather than pasting generated OpenAPI schemas in full. Update
this page when protocol models gain or change fields.
