# MAIL Documentation

This directory is the canonical documentation home for active MAIL v2 work.
MAIL uses the [Divio documentation system][divio-about], so each page belongs
to exactly one of four categories.

## Start Here

- New to MAIL: follow [Run MAIL Locally](tutorials/run-local-mail.md).
- Trying to complete a known task: browse [How-To Guides](howtos/README.md).
- Looking up commands, models, or endpoints: browse [Reference](references/README.md).
- Trying to understand concepts and tradeoffs: browse [Explanations](explanations/README.md).

## Categories

- [Tutorials](tutorials/README.md) are learning-oriented lessons. They walk a
  beginner through a concrete project and should be tested end to end.
- [How-To Guides](howtos/README.md) are goal-oriented recipes. They answer
  "How do I ...?" questions for readers who already know the basics.
- [Reference](references/README.md) is information-oriented lookup material. It
  describes commands, APIs, models, configuration, and repository structure.
- [Explanations](explanations/README.md) are understanding-oriented discussions.
  They explain why MAIL works the way it does and how its pieces fit together.

## Proposed Layout

### Tutorials

- [Run MAIL Locally](tutorials/run-local-mail.md)
- [Send Your First MAIL Message](tutorials/send-first-message.md)
- [Build a Minimal HTTP Client](tutorials/build-minimal-http-client.md)

### How-To Guides

- [Initialize the Memory Backend](howtos/initialize-memory-backend.md)
- [Run the MAIL Server](howtos/run-server.md)
- [Run the MAIL Daemon](howtos/run-daemon.md)
- [Authenticate a User-Agent](howtos/authenticate-user-agent.md)
- [Send a Message with the CLI](howtos/send-message-cli.md)
- [Manage User-Agents](howtos/manage-user-agents.md)
- [Manage Swarms](howtos/manage-swarms.md)
- [Manage Mailing Lists](howtos/manage-mailing-lists.md)
- [Regenerate API Artifacts](howtos/regenerate-api-artifacts.md)
- [Run the Test Suite](howtos/run-tests.md)

### Reference

- [Repository Layout](references/repository-layout.md)
- [Configuration](references/configuration.md)
- [Protocol Specification](references/protocol-specification.md)
- [HTTP API](references/http-api.md)
- [Client CLI](references/client-cli.md)
- [Admin CLI](references/admin-cli.md)
- [Server CLI](references/server-cli.md)
- [Daemon CLI](references/daemon-cli.md)
- [Data Models](references/data-models.md)
- [Storage Backends](references/storage-backends.md)

### Explanations

- [MAIL v2 Overview](explanations/mail-v2-overview.md)
- [Architecture](explanations/architecture.md)
- [Addressing Model](explanations/addressing-model.md)
- [Delivery Model](explanations/delivery-model.md)
- [Security Model](explanations/security-model.md)
- [MAIL v1 Legacy Runtime](explanations/mail-v1-legacy.md)
- [Documentation System](explanations/documentation-system.md)

## Existing Source Material

- Protocol source of truth: [../spec/SPEC.md](../spec/SPEC.md) and
  [../spec/openapi.yaml](../spec/openapi.yaml)
- Active package docs to migrate or consolidate:
  [client docs](../src/mail/client/docs/README.md) and
  [server docs](../src/mail/server/docs/README.md)
- Archived MAIL v1 material:
  [legacy README](../src/mail/legacy/README.md) and
  [legacy docs](../src/mail/legacy/docs/README.md)

## Writing Rules

- Keep a page in one category. If a page starts teaching, solving, describing,
  and discussing at once, split it.
- Keep tutorials robust and repeatable. They should avoid optional branches and
  should show visible progress quickly.
- Keep how-to guides task-focused. Link to explanations instead of pausing for
  conceptual discussion.
- Keep reference pages close to the implementation and generated contracts.
  Command and API references should point at their source files.
- Keep explanations free to discuss motivation, alternatives, and tradeoffs, but
  link out to tutorials, how-tos, and reference pages for action or lookup.

[divio-about]: https://docs.divio.com/documentation-system/
[divio-tutorials]: https://docs.divio.com/documentation-system/tutorials/
[divio-howtos]: https://docs.divio.com/documentation-system/how-to-guides/
[divio-references]: https://docs.divio.com/documentation-system/reference/
[divio-explanations]: https://docs.divio.com/documentation-system/explanation/
