# MAIL v2 Overview

Status: draft

## What MAIL is

The Multi-Agent Interface Layer (MAIL) is an open protocol for **email-like
communication** between humans and AI agents. It defines three things: a set of
data-structure primitives (messages, drafts, boxes, swarms, lists), an HTTP
contract for client–server interaction, and the terminology and rules that tie
them together. Participants — human users, AI agents, delivery daemons — are
addressable *user-agents* with their own inboxes, and they exchange messages much
as people exchange email.

## The problem v2 solves

MAIL v1 defined an inter-agent messaging contract *and* prescribed how
multi-agent systems should run: their runtime environment, tool usage, and
execution model. By 2026 that coupling looked like a mistake. Terminal-style
agents showed that an agent's runtime does not need to be defined in the same
place as its communication contract.

MAIL v2 draws a hard line: it specifies the **communication layer and as little
else as possible**. Two goals drive it (SPEC §3.1):

- **Focus on communication.** Runtime, tool execution, and agent internals are
  explicitly out of scope.
- **Don't reinvent the wheel.** Where good standards already exist (HTTP, OAuth2,
  JSON, RFC-3339 timestamps), MAIL builds on them rather than redefining them.

## Why the repository is split into packages

The refocus is reflected in the code layout. Instead of one runtime, v2 is four
small workspace packages with a single responsibility each — a shared protocol
contract, a server, a client, and a delivery daemon (see
[Architecture](architecture.md) and [Repository Layout](../references/repository-layout.md)).
This keeps the wire contract (`mail-swarms-protocol`) independent of any one
implementation, so alternative servers or clients can conform to the same
protocol.

## What MAIL is not (SPEC §3.2)

- **Not an agent runtime.** MAIL does not say how an agent thinks, acts, or runs;
  it only carries messages between agents.
- **Not the only way agents may communicate.** MAIL mirrors email — ubiquitous,
  but not the sole channel. Agents are free to use whatever else fits a given
  job; MAIL is the shared, email-like layer, not a mandate for *all* inter-agent
  traffic.

## Related pages

- [Run MAIL Locally](../tutorials/run-local-mail.md) — see it work end to end.
- [Architecture](architecture.md) — how the pieces fit together.
- [Protocol Specification](../references/protocol-specification.md) — the
  normative source.
- [MAIL v1 Legacy Runtime](mail-v1-legacy.md) — what the archived v1 code is.
