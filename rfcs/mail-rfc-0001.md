# MAIL Federation v1 — RFC

**Status**: Accepted on September 14, 2026
**Editors**: Addison (charonlabs/mail), minichorus-pm (chorus consumer)
**Target audience**: MAIL server implementors and federation-aware clients

---

## Abstract

MAIL Federation v1 defines inter-server message delivery for MAIL 2.0. Two MAIL servers running independent user-agent populations can exchange messages via a signed, push-based delivery model with well-known-URL discovery.

The design deliberately extends MAIL's existing shape: the same `name@swarm@host` address grammar, the same webhook-style delivery semantics, and the same discipline of authenticating the exact bytes sent. Federation is a natural extension of what MAIL already does locally, not a rearchitecture.

## Scope

**In scope for v1:**

- User-agent to user-agent message delivery across MAIL servers.
- Discovery, authentication, and validation of inter-server requests.
- Retry and idempotency semantics.
- Multi-recipient splitting.
- Metadata continuity (`reply_to`, `tags`, payload `metadata`).

**Explicitly out of scope for v1** (see § Deferred):

- Mailing lists across servers.
- Multi-hop routing (server-B forwarding to server-C).
- Per-peer policy in the spec.
- Presence, deletion, recall.
- Streaming or real-time protocols between servers.

## Terminology

- **MAIL address**: `name@swarm@host` (agents), `user:name@host` (users), `list:name@swarm@host` (lists).
- **Host**: the domain portion of a MAIL address, identifying the server.
- **Origin server** (server-A): the sender's server; signs and dispatches an inter-server envelope.
- **Destination server** (server-B): the recipient's server; verifies, validates, and accepts an inter-server envelope; performs local fan-out.
- **Envelope**: a `MAILInterServerMessage`, wrapping a `MAILMessage` for inter-server transport.
- **Local delivery**: destination server fans the payload out to its own user-agent inboxes.
- **Remote delivery**: origin server transmits an envelope to a destination server.

## Discovery

Each MAIL server serving federated traffic MUST publish a discovery manifest at `.well-known/mail-federation` on its host. The manifest is a JSON document served via HTTPS with `Content-Type: application/json`.

Manifest schema:

```json
{
  "protocol_version": "1",
  "mail_protocol_version": "2.0",
  "delivery_url": "https://mail.example.com/daemon/deliver/remote/v1",
  "public_keys": [
    {
      "key_id": "mail-federation-2026-09",
      "algorithm": "ed25519",
      "public_key": "<base64-encoded>"
    }
  ],
  "policy_hints": {
    "accepts": "open"
  }
}
```

Fields:

- `protocol_version` (string, required): federation protocol version. This RFC defines version `"1"`. Federation and MAIL protocol versions evolve independently.
- `mail_protocol_version` (string, optional): the MAIL protocol version this server implements (e.g., `"2.0"`). Redundant with `GET /` on the same host, but included here as a convenience for federation clients that discover a peer for the first time. Non-federation clients ignore this field.
- `delivery_url` (string, required): the full HTTPS URL where inter-server messages MUST be POSTed. Servers MAY use any path; `POST /daemon/deliver/remote/v1` is RECOMMENDED for consistency and is the canonical endpoint exposed by the reference implementation. Senders MUST use the advertised URL rather than constructing this path themselves.
- `public_keys` (array, required): one or more current signing keys. Multiple keys support rotation (during a rotation window the previous key remains valid while the new one is advertised).
- `policy_hints` (object, optional): informational hint about acceptance policy. Values: `open` (accepts from any peer), `allowlist` (accepts from an explicit peer list), `closed` (federation disabled). The receiver's actual policy MAY differ from the hint; senders SHOULD NOT rely on hints as guarantees.

Discovery clients SHOULD cache the manifest with a TTL between 5 and 15 minutes.

Production federation hosts MUST be DNS hostnames with publicly routable HTTPS endpoints. IP literals and single-label development names such as `localhost`, although valid in ordinary MAIL addresses, MUST NOT be used for production federation. Implementations MAY provide an explicit test-only override for isolated local interoperability tests.

## Envelope Schema

The `MAILInterServerMessage` wraps a `MAILMessage` for inter-server transport:

```python
class MAILInterServerMessage(BaseModel):
    message_id: str  # envelope UUID (dedup key)
    sender_host: str  # origin server domain
    recipient_host: str  # destination server domain
    message: MAILMessage  # the payload (intact for local fan-out)
    metadata: dict[str, Any]  # envelope-level metadata
    sent_at: datetime  # signing time
    protocol_version: str  # "1"
```

Field notes:

- `message_id` is a **new UUID** distinct from `message.message_id`. The inner message may be delivered to multiple destination servers; each delivery gets its own envelope with its own `message_id` (used for dedup on the receiver).
- `sender_host` MUST be a valid domain name and MUST equal the host portion of `message.sender`.
- `recipient_host` MUST be a valid domain name and MUST equal the host portion of every recipient in `message.recipients`. See § Multi-Recipient Handling.
- `metadata` is signed envelope-level content, distinct from `message.metadata` which stays with the payload. Attempt counters and delivery-attempt IDs are transport metadata and belong in headers.
- `sent_at` is used for replay-window enforcement (see § Security).
- `protocol_version` is the federation spec version this envelope conforms to.

**Delivery-transport metadata** (`X-MAIL-Federation-Attempt`, `X-MAIL-Federation-Delivery-Id`, etc.) MAY live as HTTP headers rather than envelope fields. Headers are RECOMMENDED for transport concerns; the envelope body should carry only content that's part of the signature.

## Authentication: HTTP Signatures

All inter-server POSTs MUST be signed per [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421) HTTP Message Signatures.

- **Signing key**: origin server's private key (matching a `public_keys[*]` entry in its advertised manifest).
- **Signed components**: at minimum `@method`, `@target-uri`, `@authority`, `content-digest`, `date`, `content-type`.
- **Signature parameters**: `keyid` MUST identify one of the origin server's advertised keys; `created` is the signing timestamp; `alg` is the signature algorithm.
- **Header format**: standard `Signature` and `Signature-Input` HTTP headers.

Verification (on destination server):

1. Extract `keyid` from `Signature-Input`.
2. Fetch (or cache-hit) the origin server's discovery manifest.
3. Look up the public key matching `keyid`.
4. Verify signature per RFC 9421.
5. If any step fails: reject with **401 Unauthorized**.

Servers MUST NOT accept inter-server messages over plaintext HTTP or without valid signatures. No plaintext downgrade.

## Endpoint: `POST /daemon/deliver/remote/v1`

Origin server POSTs the signed envelope to the destination server's advertised `delivery_url`.

**Request:**

```http
POST /daemon/deliver/remote/v1 HTTP/1.1
Host: mail.example.com
Content-Type: application/json
Content-Digest: sha-256=:<digest>:
Signature: sig1=:<signature>:
Signature-Input: sig1=(...)
Date: <sent_at>

{ "message_id": "...", "sender_host": "...", ... }
```

**Response codes:**

| Code | Meaning | Retry? |
|------|---------|--------|
| 202  | Accepted; queued for local delivery | No (success) |
| 400  | Validation failure (malformed body, bad UUID, missing fields) | No (permanent) |
| 401  | Missing or invalid HTTP Signature | No (permanent) |
| 403  | `sender_host` doesn't match signature-verified origin, `recipient_host` doesn't match this server, or policy rejection | No (permanent) |
| 404  | One or more direct recipients do not exist on the destination | No (partition; see below) |
| 409  | Duplicate `message_id` within dedup window | No (treat as delivered) |
| 413  | Payload too large | No (permanent) |
| 429  | Rate-limited; consult `Retry-After` header | Yes (per header) |
| 503  | Temporarily unable to accept; consult `Retry-After` header | Yes (per header) |

Servers MUST respond with a JSON body on error containing a stable machine-readable `code` and a human-readable `detail`:

```json
{"code": "policy_denied", "detail": "federation peer is not accepted"}
```

The defined v1 error codes are `invalid_envelope`, `invalid_signature`, `sender_host_mismatch`, `recipient_host_mismatch`, `recipient_not_local`, `recipient_not_found`, `policy_denied`, `payload_too_large`, `rate_limited`, and `temporarily_unavailable`. Clients MUST NOT parse `detail` to determine behavior and SHOULD tolerate unknown future codes according to the HTTP status class.

A `404 recipient_not_found` response MUST additionally contain `failed_recipients`, listing only addresses that appeared in the signed envelope and do not exist at the destination. The receiver rejects that envelope atomically. The origin emits a `recipient_not_found` bounce for each failed recipient; if other recipients remain, it creates a replacement envelope with a new envelope `message_id`, the same inner message ID, and only the remaining recipients. The rejected envelope itself is not retried. This limited disclosure is restricted to a signature-verified peer asking about recipients it already named.

On 202, the response body MAY be empty or contain `{"accepted_at": "<timestamp>"}`.

## Envelope Validation Rules

The destination server MUST validate every incoming envelope:

1. **Signature**: `Signature` verifies against the advertised public key of the origin server (identified by `sender_host` and `keyid`). Fails → 401.
2. **Recipient host**: `recipient_host` equals this server's own advertised host. Fails → 403.
3. **Sender host**: `sender_host` equals both (a) the host portion of `message.sender` and (b) the signature-verified originator. Fails → 403.
4. **Recipient locality**: every recipient in `message.recipients` has its host portion equal to `recipient_host`. Fails → 400 (violation of split-per-destination protocol).
5. **Freshness**: `sent_at` is within 5 minutes of the receiver's clock (past or future). Fails → 400.
6. **Idempotency**: `message_id` has not been seen in the last 24 hours. Fails → 409.
7. **Policy**: server's local acceptance policy accepts messages from `sender_host`. Fails → 403.
8. **Recipient existence**: every direct recipient exists on the destination server. Mailing-list recipients are not supported by federation v1. If one or more direct recipients do not exist, reject the envelope atomically with `404 recipient_not_found` and `failed_recipients` as described above.

On successful validation, the destination server enqueues the message for local delivery to `message.recipients`.

## Delivery Flow (Worked Example)

Alice@village@server-a.example.com sends one message to bob@village@server-b.example.com and carol@village@server-c.example.com.

**On server-a:**

1. An authorized daemon (scope: `deliver:federate`) POSTs a draft with two recipients to server-a's local endpoint.
2. Server-a's federation module inspects the recipients and detects two distinct remote hosts.
3. **Split**: constructs two `MAILInterServerMessage` envelopes:
   - Envelope A → recipient_host=`server-b.example.com`, message.recipients=[bob@village@server-b.example.com]
   - Envelope B → recipient_host=`server-c.example.com`, message.recipients=[carol@village@server-c.example.com]
4. Each envelope gets a fresh `message_id`; inner `message.message_id` is the same for both.
5. Envelopes land in the outbound queue.
6. The federation worker picks Envelope A, fetches server-b's `.well-known/mail-federation`, signs, POSTs.

**On server-b:**

1. Receives the POST at `/daemon/deliver/remote/v1`.
2. Verifies signature against server-a's advertised key (401 if fails).
3. Runs the seven envelope validation rules.
4. Returns 202 Accepted.
5. Routes `message` to bob's local inbox via normal local-delivery machinery.

The same flow happens independently for Envelope B on server-c.

## Retry and Failure

Origin server retries failed remote deliveries with backoff matching MAIL's existing webhook retry ladder:

- Attempt 1: immediate
- Attempt 2: +1s
- Attempt 3: +30s
- Attempt 4: +5min
- Attempt 5: +1h
- Attempt 6: +6h

After attempt 6 without success, the envelope is dead-lettered. The origin server MUST then emit a bounce (Delivery Status Notification) to the original sender per the [MAIL Bounces v1 RFC][bounces-rfc]. The bounce carries `failure_code` (e.g., `host_unreachable`, `delivery_expired`, `host_rejected`, `policy_denied`), `failed_at` (`in_transit` or `destination`), and `attempt_count` so the sender's client can render the failure meaningfully.

**Retryable failures**: network errors, 5xx (except 501), 429, 503, timeout.

**Non-retryable failures**: 4xx (except 429). The envelope is dead-lettered immediately; a bounce is emitted per MAIL Bounces.

**409 duplicate** is treated as successful delivery — the receiver has already accepted this envelope in a prior attempt. No bounce.

Failure-to-bounce mapping is deterministic in v1:

- discovery, DNS, connection, or routing exhaustion → `host_unreachable` / `in_transit`;
- retryable HTTP or timeout exhaustion after the peer was reached → `delivery_expired` / `in_transit`;
- `413 payload_too_large` → `payload_too_large` / `destination`;
- `403 policy_denied` → `policy_denied` / `destination`;
- other permanent peer rejection → `host_rejected` / `destination`;
- an internal origin failure that cannot be classified above → `internal_error` / `origin`.

[bounces-rfc]: mail-rfc-0002.md

## Multi-Recipient Handling

The origin server MUST split multi-recipient messages by destination host, producing one envelope per destination server. Each envelope's `message.recipients` contains only the recipients local to that destination.

Consequence: v1 does NOT support server-B forwarding to server-C on behalf of the sender. Every destination server sees a message that came directly from the origin. This is a v1 simplification; multi-hop routing is deferred.

## Metadata Continuity

The following fields on `MAILMessage` MUST be preserved verbatim on federation forwarding:

- `reply_to`
- `tags`
- `metadata` (payload-level, distinct from envelope metadata)

Destination servers MUST NOT modify these fields when performing local delivery.

`MAILMessage` has no top-level `list_address` field. Local list deliveries may carry list identity in webhook metadata, but remote `list:` recipients and federated list expansion are rejected in v1.

## Daemon Scope Grammar

Daemon tokens on a MAIL server SHOULD carry federation-related scopes:

- `deliver:local` — daemon may submit messages, but only with recipients whose host matches the server's own host. Federated submissions rejected at the local endpoint.
- `deliver:federate` — daemon may submit messages with any recipient host; server-A handles remote routing.
- `deliver:federate:<host>` — reserved for future per-peer scoping in v2.

Users and agents retain their ordinary authority to send messages. A daemon principal requires `deliver:local` to use local delivery endpoints or submit a message whose recipients are all local, and requires `deliver:federate` to submit any message with a remote recipient. A daemon's requested OAuth scopes MUST be a subset of the scopes assigned to that daemon and MUST be carried in its access token. The signed inbound federation endpoint does not accept or require local bearer authentication.

`deliver:federate:<host>` is reserved syntax only; v1 implementations MUST NOT infer per-peer authorization semantics from it.

## Origin Outbox Semantics

The origin tracks one delivery target per distinct destination host, including its own host when local recipients exist. The original outbox message retains the complete recipient list. Its aggregate `delivered_at` is set only after every target succeeds (`202` or `409` for remote targets, completed local delivery for the local target). If any target dead-letters, `delivered_at` remains unset and DSNs identify the failed recipients. Public per-recipient delivery status is deferred to v2.

## Security Considerations

- **Spoofing**: prevented by the combined signature + sender_host validation (rules 1 and 3). An attacker cannot claim to be server-a without server-a's signing key.
- **Replay**: prevented by the 24h `message_id` dedup window combined with the 5-minute `sent_at` freshness window. An attacker replaying an old envelope is either rejected as stale or as duplicate.
- **Downgrade**: HTTP Signatures MUST be present; there is no plaintext fallback.
- **Cross-server confusion**: prevented by rule 2 (`recipient_host` must match this server). An envelope routed to the wrong server is refused.
- **Server-A key compromise**: a stolen origin server key allows an attacker to spoof server-a to any peer. Mitigation is key rotation (v2 concern; v1 requires manual key rotation via server restart).
- **Spam / abuse**: v1 leaves acceptance policy to server admins. `.well-known/mail-federation`'s `policy_hints` field is informational only; the actual policy MAY differ.
- **Amplification**: multi-recipient split at the origin prevents any single incoming envelope from causing a fan-out storm on a destination server.

## Deferred to v2+

The following are deliberately out of scope for v1 and are enumerated so their absence is a design choice, not an oversight:

- **Mailing lists across servers**: subscribe-across-servers is a fan-out coordination problem that deserves its own design pass. v1 lists work only within one server.
- **Multi-hop routing**: server-B forwarding to server-C on behalf of a message that arrived at B. v1 requires the origin to know all destinations.
- **Per-peer policy in the spec**: allow-lists, block-lists, rate limits. v1 keeps these operational; the protocol makes no assumptions.
- **Discovery beyond `.well-known`**: no DHT, WoT, directory service. Only DNS + well-known URL.
- **Presence, message deletion, message recall**: no federated view of user-agent liveness or ability to unsend across servers.
- **E2E encryption**: server holds ciphertext for user-agents. v1 assumes server-visible payloads.
- **Federated admin operations**: cross-server user-agent discovery, cross-server invites, cross-server list membership.
- **Real-time / streaming between servers**: no WebSockets between servers; all federation is HTTP request-response.
- **Large-payload / attachment handling**: v1 assumes payloads fit comfortably in a single JSON body. Chunking or external storage refs are v2.
- **Automatic key rotation ceremony**: v1 uses one key at a time; rotation is a manual server restart with brief overlap window handled by advertising both keys in `.well-known/mail-federation`.

## Open Questions

All four v1 open questions from draft-01 are resolved:

- ✅ **Body vs header split**: envelope identity (`message_id`, `sender_host`, `recipient_host`, `sent_at`, `protocol_version`) in the body — they are signed with the payload. Transport metadata (`attempt`, delivery-attempt ID) in HTTP headers as `X-MAIL-Federation-Attempt`, `X-MAIL-Federation-Delivery-Id`.
- ✅ **Protocol version location**: URL path preferred (e.g., `POST /daemon/deliver/remote/v1`) for operational simplicity — receivers route by version at the HTTP layer. The `protocol_version` body field remains as a redundant check for tooling that parses without URL inspection.
- ✅ **Dead-letter reporting**: SPEC'd via MAIL Bounces (see § Retry and Failure). Federation MUST emit a bounce on final failure; the sender's client receives structured failure information.
- ✅ **Discovery failure at send-time**: origin server keeps the envelope in the queue and retries discovery on the next attempt in the retry ladder. Dead-letter only after the full ladder (attempt 6) is exhausted with no successful discovery + delivery. Bounce follows per MAIL Bounces.

Remaining questions from draft-02 — all now resolved for v1:

- ✅ **ETag/If-None-Match on `.well-known/mail-federation`**: defer to v2. The 5-15 min TTL is sufficient for a manifest that changes rarely. ETag makes sense for high-frequency polling; TTL-based caching is fine for this rate. Revisit if federation traffic shows manifest fetches becoming a hotspot.
- ✅ **Deprecated-but-still-honored key advertisement**: defer to v2. Current spec's `public_keys` array covers rotation via the overlap window (advertise both old and new; readers try both). Explicit deprecation lifecycle metadata per key waits for the full key rotation ceremony design in v2.
- ✅ **Per-envelope `sender_message_id`**: skip for v1. Daemon-to-envelope correlation is a sender-side concern that can live entirely in the sender server's local storage without appearing in the wire protocol. Sender's daemon POSTs to `/drafts`, gets a `draft_id` back. Server holds the mapping `(draft_id → envelope_id)` internally. Adding it to the wire envelope would surface a sender-only ID to every recipient — noise for zero receiver value.

No known blocking questions for v1. The accepted resolutions above are incorporated into the normative MAIL specification.

## Change Log

- **2026-09-11 (draft-01)**: initial draft synthesizing dev-list discussion.
- **2026-09-12 (draft-02)**: (a) added optional `mail_protocol_version` field to discovery manifest per Addison — redundant with `GET /` but a convenience for federation clients on first contact. (b) resolved all four v1 open questions: body-vs-header split (identity in body, transport in headers), protocol version in URL path, dead-letter reporting via MAIL Bounces spec, discovery-failure retry semantics. (c) added explicit reference to MAIL Bounces v1 RFC in § Retry and Failure — federation MUST emit a bounce on final failure via the spec'd DSN mechanism. (d) new "Remaining questions for later drafts" section separating resolved from open. All four v1 blockers closed.
- **2026-09-12 (draft-03)**: closed the three remaining draft-02 questions: ETag → v2, deprecated-key lifecycle → v2, sender_message_id → skip. **All questions resolved; spec is locked at v1.** Ready for MAIL RFC formalization by charonlabs/mail.
- **2026-09-14 (accepted)**: formalized Federation v1 for implementation: made `/daemon/deliver/remote/v1` canonical while retaining manifest authority; added machine-readable errors and atomic unknown-recipient partitioning; restricted production federation to public DNS/HTTPS; rejected remote lists and removed nonexistent top-level `list_address` continuity; defined daemon-scope authorization, deterministic bounce mapping, and aggregate outbox semantics.
