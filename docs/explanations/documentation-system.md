# Documentation System

Status: draft

MAIL's docs follow the [Divio documentation system][divio] (also called
Diátaxis): every page belongs to exactly one of four categories, each serving a
different reader need. This page explains how to decide where a new page belongs
and why the separation matters. The index and writing rules live in
[docs/README.md](../README.md).

## The four categories

| Category | Serves | Reader is… | Optimizes for |
| --- | --- | --- | --- |
| **[Tutorial](../tutorials/README.md)** | Learning | a beginner following along | a guaranteed, repeatable success |
| **[How-to guide](../howtos/README.md)** | A task | someone who knows the basics | getting a specific job done |
| **[Reference](../references/README.md)** | Looking up | someone who knows what they want | accuracy and completeness |
| **[Explanation](README.md)** | Understanding | someone thinking about the system | context, motivation, tradeoffs |

The split is really two axes: *practical* (tutorials, how-tos) vs *theoretical*
(reference, explanation), and *studying* (tutorials, explanation) vs *working*
(how-tos, reference). A page should sit in one cell of that grid.

## Why mixed-purpose pages fail

A page that teaches, solves a task, lists exact fields, *and* argues motivation
all at once serves no reader well: the beginner drowns in reference detail, the
practitioner wades through backstory to find a command, and the lookup reader
can't trust a page that also editorializes. Mixed pages also rot faster, because a
change to the API forces edits to prose that was really about concepts. Keeping
each page to one job keeps it short, trustworthy, and cheap to maintain.

## How to place (or split) a page

Ask **what the reader is doing** when they open it:

- *"Walk me through my first success."* → Tutorial. Avoid optional branches; show
  visible progress fast; it must run end to end.
- *"How do I do X?"* → How-to. Assume basics; stay task-focused; link out to
  explanations instead of pausing to teach concepts.
- *"What are the exact endpoints / fields / flags?"* → Reference. Mirror the
  implementation; prefer generated artifacts; keep opinion out.
- *"Why does it work this way?"* → Explanation. Discuss motivation and
  alternatives; link to tutorials, how-tos, and reference for action and lookup.

If a proposed page answers more than one of these, split it and cross-link the
parts. A common shape in this repo: an explanation (e.g.
[Mailing Lists](mailing-lists.md)) paired with a how-to
([Manage Mailing Lists](../howtos/manage-mailing-lists.md)) and a reference
([HTTP API](../references/http-api.md)).

## Naming conventions

- **Tutorials** read as an outcome or a journey: *Run MAIL Locally*, *Send Your
  First MAIL Message*.
- **How-tos** are imperative tasks: *Manage Swarms*, *Authenticate a User-Agent*.
- **Reference** pages are noun topics: *HTTP API*, *Data Models*, *Configuration*.
- **Explanations** are concept nouns: *Delivery Model*, *Security Model*.

Files are kebab-cased within the category directory
(`howtos/manage-swarms.md`); reference pages that mirror generated artifacts note
that they are generated (e.g. the CLI references).

## Migrating package-local and legacy docs

Some packages still carry their own `docs/` (`src/mail/server/docs/`,
`src/mail/client/docs/`) that predate this set, and the v1 archive has its own
docs under `src/mail/legacy/docs/`. This top-level tree is canonical; migrate
package-local material into the right category here and treat legacy docs as
historical reference (see [MAIL v1 Legacy Runtime](mail-v1-legacy.md)).

## Related pages

- [Tutorials](../tutorials/README.md)
- [How-To Guides](../howtos/README.md)
- [Reference](../references/README.md)
- [Explanations](README.md)

[divio]: https://docs.divio.com/documentation-system/
