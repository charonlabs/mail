# Protocol Specification

Status: draft

MAIL has two normative artifacts, both under [`spec/`](../../spec). This page
orients you to them and maps each part of the specification to the implementation
reference pages in this set. It does not restate the spec — read the source files
for the authoritative text.

- **[`spec/SPEC.md`](../../spec/SPEC.md)** — the protocol prose. Versioned,
  written in [RFC 2119][rfc-2119] requirements language (MUST / SHOULD / MAY).
  It defines terminology, user-agent categories, address forms, the message
  contract, and delivery responsibilities.
- **[`spec/openapi.yaml`](../../spec/openapi.yaml)** — the authoritative HTTP
  wire contract. It is **generated** from the running FastAPI app, not hand-authored
  (see [Regenerate API Artifacts](../howtos/regenerate-api-artifacts.md)), so it
  always matches the server's declared routes and schemas.

## Version and status

| Field | Value |
| --- | --- |
| Version | `2.0` |
| Date | June 10, 2026 |
| Status | Open to feedback |

Versions follow `{major}.{minor}` (SPEC §10). Message payloads carry the version
in `mail_version`, which MUST be `"2.0"` for this revision.

## Section map

| SPEC.md section | Topic | Where it lives in these docs |
| --- | --- | --- |
| §3 Motivation | Goals; what MAIL is *not* | [MAIL v2 Overview](../explanations/mail-v2-overview.md) |
| §4 Architecture | Clients, servers, swarms | [Architecture](../explanations/architecture.md) |
| §5 User-Agents | admin / agent / daemon / user | [Data Models](data-models.md) |
| §6 Addresses | Host- vs swarm-scoped forms | [Addressing Model](../explanations/addressing-model.md) |
| §7 Messages | Message fields, replies, tags | [Data Models](data-models.md) |
| §8 Delivery | Pre-send vs post-send errors | [Delivery Model](../explanations/delivery-model.md) |
| §9 Security | Trust boundaries per component | [Security Model](../explanations/security-model.md) |
| §10 Versioning | Protocol version rules | this page |

## OpenAPI contract role

The OpenAPI document is the source of truth for endpoints, parameters, request
bodies, response schemas, and status codes. Client and server implementers MUST
conform to it (SPEC §4.1, §4.2). Because it is generated from the app, the
[HTTP API](http-api.md) reference is navigational — it points into the generated
schema rather than duplicating it.

## Contract test coverage

Conformance is enforced by the suite in [`tests/contract/`](../../tests/contract):

- `test_spec_addresses.py` — address-shape rules from SPEC §6.
- `test_spec_messages.py` — message field constraints from SPEC §7.
- `test_spec_delivery.py` — delivery semantics from SPEC §8.
- `test_openapi_drift.py` — the committed `spec/openapi.yaml` matches the app.
- `test_openapi_request_bodies.py` — body-bearing endpoints document their bodies.

Run them via [Run the Test Suite](../howtos/run-tests.md).

## Known spec ↔ implementation divergences

The reference implementation intentionally (or incidentally) differs from the
prose in a few places. These are tracked here so readers trust the code over the
prose where they disagree:

- **Identifier length cap.** SPEC §6 says agent / user / admin / daemon-worker /
  swarm / list identifiers "SHOULD be no longer than **32** characters." The
  reference implementation enforces a hard cap of **31**
  (`core/constants.py`: `*_NAME_LEN_MAX = 31`), rejecting longer values with a
  validation error. Message tags, by contrast, use a cap of 32 in both
  (`MESSAGE_TAG_LEN_MAX = 32`, matching SPEC §7.10). This name-length mismatch
  is unresolved — see the maintenance note below.

## Maintenance notes

Do not copy the specification text into this page; keep it as an index that links
to the exact normative files. When the implementation and `SPEC.md` are
reconciled (e.g. the 31-vs-32 identifier cap), update both the divergences list
here and [Addressing Model](../explanations/addressing-model.md).

[rfc-2119]: https://datatracker.ietf.org/doc/html/rfc2119
