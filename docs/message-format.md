# Message Format

MAIL messages are strongly typed envelopes used internally and over interswarm HTTP. See src/mail/core/message.py and the JSON Schemas in spec/.

Addresses
- MAILAddress: `{ "address_type": "agent"|"user"|"system", "address": "string" }`
- Helpers: `create_agent_address`, `create_user_address`, `create_system_address`
- Interswarm routing uses `agent@swarm` in `address`

Core envelopes
- MAILRequest
  - `task_id`, `request_id`, `sender`, `recipient`, `subject`, `body`
  - Optional interswarm: `sender_swarm`, `recipient_swarm`, `routing_info`
- MAILResponse
  - `task_id`, `request_id`, `sender`, `recipient`, `subject`, `body`
  - Optional interswarm: `sender_swarm`, `recipient_swarm`, `routing_info`
- MAILBroadcast
  - `task_id`, `broadcast_id`, `sender`, `recipients[]`, `subject`, `body`
  - Optional interswarm: `sender_swarm`, `recipient_swarms[]`, `routing_info`
- MAILInterrupt
  - `task_id`, `interrupt_id`, `sender`, `recipients[]`, `subject`, `body`
  - Optional interswarm: `sender_swarm`, `recipient_swarms[]`, `routing_info`

Wrapper for interswarm HTTP
- MAILInterswarmMessage
  - `message_id`, `source_swarm`, `target_swarm`, `timestamp`
  - `payload`: one of the core envelopes
  - `msg_type`: `request|response|broadcast|interrupt`
  - `auth_token` (optional), `metadata` (optional)

XML helper
- The runtime can render a human-readable XML body for LLM input: `build_mail_xml(message)`

Schemas and examples
- Spec JSON Schemas: spec/MAIL-core.schema.json, spec/MAIL-interswarm.schema.json
- Examples: spec/examples/

