# Examples

## Overview
- **Purpose**: Concrete JSON samples that validate against the MAIL schemas.
- **Usage**: Inspect as documentation, and validate with `python spec/validate_samples.py`.

## Files
- **[mail_message_request.json](/spec/examples/mail_message_request.json)**: Local request created by the server when a user calls `/message`.
  - Flow: User → `MAILRequest` to entrypoint → local routing.
  - Schema: `MAILMessage` with `msg_type="request"`.
- **[mail_message_response.json](/spec/examples/mail_message_response.json)**: Local agent-to-agent response (e.g., `weather` → `supervisor`).
  - Flow: Agent response consumed by `supervisor` during a task.
  - Schema: `MAILMessage` with `msg_type="response"`.
- **[mail_message_broadcast.json](/spec/examples/mail_message_broadcast.json)**: System/agent broadcast to multiple local agents.
  - Flow: Action completion announcements inside a swarm.
  - Schema: `MAILMessage` with `msg_type="broadcast"`.
- **[mail_message_interrupt.json](/spec/examples/mail_message_interrupt.json)**: Interrupt message to halt/adjust ongoing work.
  - Flow: Supervisor pauses another agent’s work.
  - Schema: `MAILMessage` with `msg_type="interrupt"`.
- **[mail_message_broadcast_complete.json](/spec/examples/mail_message_broadcast_complete.json)**: Final task completion broadcast produced by supervisor.
  - Flow: Resolves `submit_and_wait()` for the originating user request.
  - Schema: `MAILMessage` with `msg_type="broadcast_complete"`.
- **[interswarm_request.json](/spec/examples/interswarm_request.json)**: Wrapper used when sending a request to a remote swarm.
  - Flow: Swarm A → `/interswarm/message` on Swarm B (request payload inside payload).
  - Schema: `MAILInterswarmMessage` with `msg_type="request"`.
- **[interswarm_response.json](/spec/examples/interswarm_response.json)**: Wrapper used when returning a response to the origin swarm.
  - Flow: Swarm B → `/interswarm/response` on Swarm A (response payload inside payload).
  - Schema: `MAILInterswarmMessage` with `msg_type="response"`.

## Validation
- **Run**: `python spec/validate_samples.py`
- The script validates both inline samples and all files in this directory against:
  - [spec/MAIL-core.schema.json](/spec/MAIL-core.schema.json)
  - [spec/MAIL-interswarm.schema.json](/spec/MAIL-interswarm.schema.json)

## **OpenAPI**
- API description: [spec/openapi.yaml](/spec/openapi.yaml)
- Schemas are referenced via `$ref` to the JSON Schema files in [spec/](/spec/).
