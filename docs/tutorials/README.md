# Tutorials

Tutorials teach MAIL by walking a beginner through a concrete, working project.
They should assume little prior MAIL knowledge, include only the explanation
needed to complete the lesson, and be tested end to end before release.

## Planned Tutorials

| Page | Outcome | Source material |
| --- | --- | --- |
| [Run MAIL Locally](run-local-mail.md) | Start a local memory-backed server, run a daemon, and observe local delivery. | `src/mail/server/docs/tutorials/quickstart.md`, `src/mail/daemon/src/mail_daemon/maild/api.py` |
| [Send Your First MAIL Message](send-first-message.md) | Log in, compose a draft, send it, and inspect inbox/outbox state. | `src/mail/client/docs/tutorials/quickstart.md`, `src/mail/client/src/mail_client/cli.py` |
| [Build a Minimal HTTP Client](build-minimal-http-client.md) | Authenticate and interact with MAIL using raw HTTP calls. | `spec/openapi.yaml`, `src/mail/protocol/src/mail_protocol/network/` |

## Tutorial Checklist

- State the concrete thing the reader will finish with.
- Prefer one happy path over branches and alternatives.
- Include prerequisites that can be verified before step 1.
- Show expected output or observable state after major steps.
- Link to reference pages for command flags, schemas, and endpoint details.
- Link to explanations for conceptual background.
