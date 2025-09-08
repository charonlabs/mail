# MAIL Documentation Index

This folder contains focused guides for the Python MAIL reference implementation. Start here to explore key topics and deep dives.

## Core Topics

- Getting started and server endpoints: see the root `README.md` (project overview, setup, and API usage)
- Interswarm messaging overview: `INTERSWARM_README.md`
- Supervisor response flow (final response synthesis): `SUPERVISOR_RESPONSE_FLOW_SOLUTION.md`
- Broadcast handling tools for agents: `broadcast-tools.md`
- Address metadata (typed sender/recipient): `ADDRESS_METADATA_README.md`

## Swarm Registry

- Volatility and persistence behavior: `swarm_registry_config.md`
- Secure auth tokens via environment references: `swarm_registry_security.md`
- Token reference mechanics and migration helpers: `AUTH_TOKEN_REF_IMPLEMENTATION.md`

## Testing

- Test layout, fixtures, and how to run: `TESTING.md`

## Notes

- Both servers use `POST /message` for user requests.
- Persistent swarms store registry auth tokens as environment variable references (no plain tokens in persistence). Volatile swarms keep tokens in memory only.
