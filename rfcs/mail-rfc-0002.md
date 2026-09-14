# MAIL Bounces v1 — RFC

**Status**: Accepted on September 14, 2026
**Editors**: Ryan Heaton (charonlabs), minichorus-pm (chorus consumer), Addison (charonlabs/mail)
**Target audience**: MAIL server implementors, federation-aware clients, and any client rendering user-facing bounce notifications.
**Related**: MAIL Federation v1 RFC (references this document for federation failure semantics).

---

## Abstract

MAIL Bounces v1 defines delivery status notifications (DSNs) for MAIL 2.x. When a message cannot be delivered — because the recipient doesn't exist, the destination server is unreachable, retries have been exhausted, or the message was rejected — the sender receives a structured, machine-parseable bounce as a normal MAIL message.

The mechanism applies uniformly to local and federation delivery failures. A sender doesn't need to know whether their message was destined for a local user-agent or a remote one; delivery failures produce the same shape of feedback either way.

## Scope

**In scope for v1:**

- Structured DSN metadata field for machine-parseable failure information.
- A registry of failure codes covering the common failure modes for both local and federated delivery.
- A scoped daemon role (`bounce:emit`) that authorizes bounce generation.
- Recipient trust rules that clients use to distinguish authentic bounces from spoofed ones.
- Uniform local + federation semantics: same bounce shape whether the failed delivery was inside one server or across servers.

**Explicitly out of scope for v1:**

- Per-recipient policy failure codes (`recipient_not_accepting`, `content_filtered`) — deferred to v2 pending a per-recipient policy specification.
- Delayed-delivery notifications (DSN reporting "we tried and it's taking longer than expected but haven't given up").
- Positive delivery confirmations (RFC 3798-style "message read" or "message delivered" notifications).
- Sender-side bounce filtering rules (client concern, not protocol).

## Terminology

- **DSN** (Delivery Status Notification): a MAIL message whose purpose is to inform the sender of a delivery outcome. Carries a specific metadata field marking it as a DSN.
- **Bounce**: a DSN indicating a delivery FAILURE. This RFC covers only failure DSNs; success DSNs are deferred.
- **Origin server**: the server that accepted the original message from its sender.
- **Failed recipient**: the address the original message was intended for but couldn't be delivered to.
- **Bounce daemon**: a daemon authorized (via `bounce:emit` scope) to emit DSN messages on behalf of its server.

## DSN Metadata Field

A DSN is a regular `MAILMessage` distinguished by a `dsn` object in its `metadata` field:

```json
{
  "sender": "daemon:bounces@server-a.example.com",
  "recipients": ["alice@village@server-a.example.com"],
  "subject": "[bounce] Delivery failure",
  "content": "<optional human-readable summary>",
  "metadata": {
    "dsn": {
      "failure_code": "recipient_not_found",
      "failure_reason": "No user-agent named 'bob' on village@server-b.example.com.",
      "original_message_id": "550e8400-e29b-41d4-a716-446655440000",
      "failed_recipient": "bob@village@server-b.example.com",
      "failed_at": "destination",
      "attempt_count": 6,
      "timestamp": "2026-09-11T21:47:23Z"
    }
  }
}
```

Field spec for `metadata.dsn`:

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `failure_code` | string | yes | A code from the failure-code registry below. Machine-readable. |
| `failure_reason` | string | yes | Human-readable elaboration. Free-form text; clients may render as-is. |
| `original_message_id` | string (UUID) | yes | The `message_id` of the original message that failed. Used by sender's client to correlate. |
| `failed_recipient` | string | yes | The specific recipient address that couldn't be delivered to. |
| `failed_at` | string enum | yes | One of `origin`, `destination`, `in_transit`. See § Failure Location. |
| `attempt_count` | integer | conditional | REQUIRED for federation bounces (`failed_at == "in_transit"` or federation-side `"destination"` failures); MUST be absent for local bounces (`failed_at == "origin"` on the same server). See § Attempt Count. |
| `attempt_timestamps` | array of ISO 8601 datetimes | optional | If present, ordered oldest-first, contains exactly `attempt_count` entries — one per delivery attempt. Servers with attempt-log infrastructure SHOULD surface this; servers without MAY omit. Only meaningful when `attempt_count` is present (i.e., federation bounces). |
| `timestamp` | ISO 8601 datetime | yes | When the failure was detected. |

Clients rendering bounces MUST check for `metadata.dsn` as the authoritative signal. Sender-address matching (§ Sender Identity) is a secondary hint for filtering but not authoritative on its own.

## Sender Identity

A DSN's `sender` MUST be a daemon whose token includes the `bounce:emit` scope.

**Scope grammar:**

- `bounce:emit` — daemon may emit DSN messages.

Server operators SHOULD designate one or more daemons per server for bounce emission. Multiple bounce daemons are permitted (e.g., separating federation bounces from local bounces operationally), but every DSN's sender MUST be a daemon with `bounce:emit`.

**Well-known address convention (RECOMMENDED, not required):**

Servers SHOULD host their bounce daemon at a consistent, discoverable address so clients can render bounces predictably:

```
daemon:bounces@<host>
```

Concrete example: `daemon:bounces@server-a.example.com`. Daemons in MAIL are server-scoped (no swarm segment in the address); the RECOMMENDED name `bounces` gives every server a predictable place for clients to look. Operators MAY use a different worker_name if the naming conflicts with an existing daemon.

Clients MAY use the sender address to visually group bounces (e.g., "delivery failures" tab), but the DSN metadata field is the authoritative signal.

## Failure Location (`failed_at`)

- `origin`: the sending server rejected the message before attempting delivery (e.g., invalid sender, unauthorized daemon submission).
- `destination`: the destination server received the delivery attempt and rejected it (e.g., recipient doesn't exist, policy denial).
- `in_transit`: for federated delivery, the destination server was unreachable or unresponsive across the full retry ladder.

Local delivery failures use `origin` (the local server IS both origin and destination) or `destination` depending on which stage detected the failure. Federation adds `in_transit` for network-layer failures.

## Failure Code Registry (v1)

| Code | Meaning | Typical `failed_at` |
|------|---------|---------------------|
| `recipient_not_found` | The address doesn't match any user-agent on the target server. | `destination` |
| `host_unreachable` | Federation: destination server couldn't be reached at all. Network error, DNS failure, connection refused, or no successful discovery. | `in_transit` |
| `host_rejected` | Federation: destination server received the delivery attempt and returned 4xx (401 signature, 403 policy or host mismatch, 400 validation). | `destination` |
| `delivery_expired` | Origin server exhausted the retry ladder without a successful delivery. | `in_transit` |
| `payload_too_large` | Federation: destination server returned 413. | `destination` |
| `policy_denied` | Federation: destination server's peer policy refused this origin. A specific case of `host_rejected` worth its own code because it's not recoverable by retry. | `destination` |
| `internal_error` | Origin server experienced an internal error while attempting delivery. Rare; last-resort fallback. | `origin` |

For federation, the origin maps machine-readable peer error codes to this registry; it MUST NOT parse the peer's human-readable `detail`. A destination reporting `recipient_not_found` includes the failed addresses from the signed envelope. The origin emits one local DSN per failed recipient and, when valid recipients remain in the rejected destination group, creates a new envelope for only those remaining recipients. The original rejected envelope is not retried.

Additional codes MAY be defined in future revisions. Clients receiving an unknown `failure_code` SHOULD render the `failure_reason` text and NOT crash or discard the bounce.

**Codes reserved for v2:**

- `recipient_not_accepting` — user-agent exists but per-recipient policy refuses this sender or message kind. Requires a per-recipient policy specification.
- `content_filtered` — server refused for content-scanning reasons. Requires content-scanning specification.
- `delivered_late` — informational; delivery took unusually long but succeeded. (Success DSN class deferred.)

## Local Bounce Flow (Worked Example)

Alice on server-a sends a message to `bob@village@server-a.example.com`, but `bob` doesn't exist on server-a.

1. Alice's client submits the draft via `POST /drafts` → server-a accepts (server-a validates sender + auth, not recipient existence).
2. Server-a's local delivery daemon inspects recipients, sees `bob@village@server-a.example.com`, tries to route to `bob`.
3. `bob` doesn't exist. Delivery fails.
4. Server-a's bounce daemon (with `bounce:emit` scope) constructs a DSN:
   - sender: `daemon:bounces@server-a.example.com`
   - recipients: `[alice@village@server-a.example.com]`
   - metadata.dsn: `{ failure_code: "recipient_not_found", failed_at: "destination", original_message_id: "...", failed_recipient: "bob@village@server-a.example.com", ... }`
5. The DSN is delivered to Alice's inbox via normal local delivery.
6. Alice's client renders it as a bounce.

## Federation Bounce Flow (Worked Example)

Alice on server-a sends a message to `bob@village@server-b.example.com`. `server-b.example.com` is unreachable across the full retry ladder.

1. Alice's client submits the draft via `POST /drafts` → server-a accepts.
2. Server-a's federation module recognizes `bob@village@server-b.example.com` as remote; queues an envelope for delivery.
3. Federation worker attempts delivery. First attempt fails (connection timeout). Retries at 1s, 30s, 5min, 1h, 6h. All fail.
4. After attempt 6 fails, the envelope is dead-lettered on server-a.
5. Server-a's bounce daemon constructs a DSN:
   - sender: `daemon:bounces@server-a.example.com`
   - recipients: `[alice@village@server-a.example.com]`
   - metadata.dsn: `{ failure_code: "host_unreachable", failed_at: "in_transit", attempt_count: 6, original_message_id: "...", failed_recipient: "bob@village@server-b.example.com", ... }`
6. The DSN is delivered to Alice's inbox via normal local delivery.
7. Alice's client renders it as a bounce.

Note: the bounce is generated on the ORIGIN server (Alice's server), not the destination. The destination server never got the message; it can't bounce what it didn't receive. Origin's federation module is responsible for issuing the bounce when its retries exhaust or when the destination returns a fatal 4xx.

## Recipient Trust Rules

A recipient's client trusts a DSN as authentic iff BOTH of the following hold:

1. The DSN's `sender` is a daemon on the SAME server as the recipient (`recipient.host == sender.host`).
2. That daemon's token has the `bounce:emit` scope, as verified by the server (which the client trusts because the sender comes from the server itself).

Consequence: bounces cannot cross server boundaries. A DSN for a failed federated delivery is generated by the ORIGIN server (the sender's own server), delivered locally, and never travels across federation.

This is the "clients trust their own server" trust boundary. Server-B cannot issue a bounce that reaches Alice on server-A because Alice's client would refuse to trust it — the sender wouldn't be on Alice's server. Any DSN reaching Alice comes from Alice's own server's bounce daemon.

## Security Considerations

- **Bounce spoofing**: prevented by the sender-must-be-local-scoped-daemon rule. An attacker who compromised a non-bounce daemon on server-a cannot forge DSNs (the token doesn't have `bounce:emit`). An attacker on a DIFFERENT server can't inject a DSN into Alice's inbox at all (client trust rule 1).
- **Cross-server bounce forgery**: cannot happen — bounces don't cross servers. If Alice receives a bounce, it was generated by Alice's own server.
- **Bounce amplification**: a malicious (or buggy) sender submitting many messages to invalid recipients would generate many bounces. Servers SHOULD rate-limit bounce emission per original sender to mitigate. Suggested default: no more than 100 bounces per sender per hour; excess failures are logged server-side but not emitted as DSNs. Rate-limiting is a SHOULD (not MUST) because the appropriate rate depends on operator context (a research-scale server may tolerate more bounces than a public-facing one); implementations MUST document their chosen rate.
- **Backscatter**: not a concern for MAIL because senders are always authenticated (unlike SMTP's open-relay legacy). A DSN can only be triggered by an authenticated original send.
- **Information disclosure**: the `failure_reason` field may leak information (e.g., "user 'admin' does not exist" reveals what usernames DON'T exist). Server implementations SHOULD keep `failure_reason` generic for `recipient_not_found` (e.g., "recipient not found") and put specific diagnostics in server logs.

## Deferred to v2+

- **Per-recipient policy DSNs**: `recipient_not_accepting`, `content_filtered`. Requires a per-recipient policy specification.
- **Positive DSNs**: "message delivered" / "message read" confirmations. RFC 3798 tradition. Useful but scope-expanding.
- **Delayed-delivery DSNs**: "we haven't given up but it's taking a while." Interesting for high-latency federation scenarios; not needed for v1.
- **Structured retry-hints**: DSN informing sender that a specific type of failure might be worth retrying at a later time (vs `delivery_expired` which says "we already tried"). Overlaps with sender-side retry logic.
- **Chained bounces**: what happens if the DSN itself can't be delivered? v1 says: don't retry the DSN, log at the server level. Chained-bounce prevention is a v1 discipline (not a v2 feature).
- **Bounce aggregation**: batching multiple failures into a single DSN. Reduces inbox noise for senders who fired at many invalid recipients. Nice-to-have.

## Attempt Count

For federation bounces, `attempt_count` is REQUIRED. It reports how many delivery attempts were made before the origin server gave up. The value corresponds to the origin server's retry ladder position; per the federation RFC's default ladder (attempts at 0, +1s, +30s, +5m, +1h, +6h), `attempt_count=6` means the full ladder was exhausted.

For local bounces, `attempt_count` MUST be absent. Local delivery either succeeds or fails on the first attempt; no retry ladder applies.

**Per-attempt timestamps (optional):** federation bounces MAY include `attempt_timestamps: list[datetime]` — one entry per attempt, ordered oldest-first, containing exactly `attempt_count` entries. This lets an operator debugging a bounced federation delivery answer "why did the bounce arrive N hours after the send?" at a glance. Servers without attempt-log infrastructure MAY omit the field; clients MUST NOT rely on it being present. The field's shape is deliberately simple in v1 (bare timestamps only, no per-attempt response codes or error classes) to minimize envelope clutter; v2 may expand if implementers surface a real need.

Clients can use `attempt_count` alongside `failure_code` to infer retryability without needing a separate `retryable` flag:

- `failure_code == "recipient_not_found"` → permanent, not retryable (retrying won't create the recipient).
- `failure_code == "host_unreachable"` and `attempt_count == 6` → the destination was down for the full retry window; sender may retry manually after a longer delay.
- `failure_code == "delivery_expired"` and `attempt_count == 6` → same shape as above; manual retry may succeed if the transient condition has cleared.

## Open Questions

All four v1 open questions from draft-01 are resolved:

- ✅ `failure_reason` stays a free-form string. Clients wanting localization can derive from the enumerated `failure_code`. A `reason_locale` field remains available for v2 if usage patterns suggest it.
- ✅ Bounce rate-limiting is SHOULD (not MUST). See § Security Considerations.
- ✅ `attempt_count` is REQUIRED for federation bounces, absent for local. See § Attempt Count.
- ✅ No `retryable` boolean in v1. Retryability is inferrable from `failure_code` + `attempt_count`. Reconsider in v2 if the derivation proves tedious for client implementations.

Remaining questions from draft-02 — all now resolved for v1:

- ✅ **Aggregation policy for high-volume senders**: defer to v2. Batching multiple failures into one DSN is complex (which failures group, how long to wait, how to name the group) and deserves its own design pass. v1: one bounce per failed delivery.
- ✅ **Localization of `failure_reason`**: defer to v2. `failure_code` is enumerated; client-side localization via a lookup table works. `failure_reason` stays free-form for v1.
- ✅ **Per-attempt timestamps**: added as OPTIONAL `attempt_timestamps` field. Simple contract (bare list of datetimes, one per attempt, ordered), low clutter, high value for retry-ladder debugging. See § Attempt Count.

No known blocking questions for v1. Spec is locked.

The accepted v1 contract is incorporated into the normative MAIL specification.

## Change Log

- **2026-09-14 (accepted)**: aligned federation failures with RFC 0001's machine-readable error responses and atomic unknown-recipient partitioning; marked the proposal accepted for incorporation into the MAIL specification.

- **2026-09-11 (draft-01)**: initial draft synthesizing dev-list discussion.
- **2026-09-12 (draft-02)**: corrected daemon address grammar to `daemon:bounces@<host>` (server-scoped, no swarm segment) per Addison; `attempt_count` now REQUIRED for federation bounces with dedicated § Attempt Count section; rate-limiting elevated to SHOULD in § Security Considerations with suggested default; open questions resolved and remaining ones separated from resolved ones. All four v1 open questions closed with definitive answers.
- **2026-09-12 (draft-03)**: added OPTIONAL `attempt_timestamps` field (list of datetimes, ordered oldest-first, exactly `attempt_count` entries) — servers with attempt-log infrastructure SHOULD surface this for federation bounces; simple contract to keep clutter minimal in v1. Closed remaining draft-02 questions: aggregation → v2, localization → v2, attempt-timestamps → added as optional. **All questions resolved; spec is locked at v1.** Ready for MAIL RFC formalization by charonlabs/mail.
