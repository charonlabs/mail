# Explanations

Explanations discuss MAIL concepts, motivation, architecture, and tradeoffs.
They are for understanding, not for step-by-step tasks or exhaustive lookup.

## Planned Explanations

| Page | Question it answers |
| --- | --- |
| [MAIL v2 Overview](mail-v2-overview.md) | What is MAIL and what problem is v2 trying to solve? |
| [Architecture](architecture.md) | How do protocol, server, client, daemon, and backend pieces fit together? |
| [Addressing Model](addressing-model.md) | Why does MAIL use host-scoped and swarm-scoped addresses? |
| [Delivery Model](delivery-model.md) | Why are daemons responsible for message delivery? |
| [Security Model](security-model.md) | What are the main trust boundaries and risks? |
| [Mailing Lists](mailing-lists.md) | What is a list? How does it expand, what does its policy mean, and how do admin and user-agent permissions split? |
| [Webhook Delivery](webhook-delivery.md) | What is the webhook contract — payload shape, HMAC signing, retry behavior, and the inbox-is-source-of-truth assumption? |
| [MAIL v1 Legacy Runtime](mail-v1-legacy.md) | How should readers interpret the archived v1 runtime and docs? |
| [Documentation System](documentation-system.md) | How should maintainers decide where a new page belongs? |

## Explanation Checklist

- Start with a concrete question or tension.
- Discuss tradeoffs and alternatives.
- Link to tutorials for learning paths.
- Link to how-to guides for tasks.
- Link to reference pages for commands, fields, and exact contracts.
