# Addressing Model

Status: stub

## Question

Why does MAIL have both host-scoped and swarm-scoped addresses, and how should
readers reason about each form?

## Source Material

- `spec/SPEC.md` section 6
- `src/mail/protocol/src/mail_protocol/core/user_agents.py`
- `src/mail/protocol/src/mail_protocol/core/validators.py`
- `tests/contract/test_spec_addresses.py`

## Topics to Discuss

- Host-scoped identities for users, admins, and daemons.
- Swarm-scoped identities for agents and mailing lists.
- Why agent names can repeat across swarms.
- Why mailing list addresses live inside swarms.
- Validation boundaries and common mistakes.

## Related Pages

- [Data Models](../references/data-models.md)
- [Manage User-Agents](../howtos/manage-user-agents.md)
- [Manage Mailing Lists](../howtos/manage-mailing-lists.md)
