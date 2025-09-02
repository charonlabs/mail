# Broadcast Handling Tools

This document explains the two broadcast-handling tools available to agents:

- `acknowledge_broadcast`: Store the received broadcast in memory without sending any response.
- `ignore_broadcast`: Do not store or respond to the broadcast.

These tools give agents explicit control over how to treat broadcasts that are informational, low-priority, or otherwise do not require discussion.

## Availability

- Included in supervisor toolset via `create_supervisor_tools`.
- Included for action agents via `action_agent_factory`.
- Exposed as OpenAI-style function tools with the following schemas:
  - `acknowledge_broadcast`:
    - `note: string | null` (optional). Only stored internally with the acknowledgement; never sent externally.
  - `ignore_broadcast`:
    - `reason: string | null` (optional). Only used internally for logging; never sent externally.

## Runtime Behavior

- Acknowledge:
  - If called while processing a message of type `broadcast`, the broadcast is written to the agent’s memory store and no outgoing MAIL message is emitted.
  - The stored memory consists of:
    - A "user" entry containing the XML-wrapped incoming broadcast (as built by `build_mail_xml`).
    - An "assistant" entry containing `<acknowledged broadcast/>` and, when provided, the supplied `note`.
  - If invoked on a non-broadcast message, it is treated as a no-op (logged at debug level).

- Ignore:
  - No memory is written, and no outgoing MAIL message is emitted.
  - An informational log entry is produced.

- Both tools are intentionally NOT included in `MAIL_TOOL_NAMES`, so they do not produce a tool echo message in the agent’s visible history and do not trigger any mail submission.

## Memory Details

- Storage uses the configured LangMem store (`src/mail/store.py`). If Postgres is configured, it uses the Postgres-backed store; otherwise, it falls back to an in-memory store.
- Acknowledgements are stored under the namespace `"{agent_name}_memory"`.
- Current implementation stores acknowledgements regardless of the agent’s `memory` flag; it is independent of whether the agent uses memory for prompting.

## Example Tool Calls

- Acknowledge a broadcast with a note:
  ```json
  {
    "tool_name": "acknowledge_broadcast",
    "tool_args": { "note": "FYI: roadmap saved for later review." }
  }
  ```

- Acknowledge a broadcast without a note:
  ```json
  {
    "tool_name": "acknowledge_broadcast",
    "tool_args": {}
  }
  ```

- Ignore a broadcast with an internal reason:
  ```json
  {
    "tool_name": "ignore_broadcast",
    "tool_args": { "reason": "Not relevant to security agent." }
  }
  ```

## When To Use

- Use `acknowledge_broadcast` when the content may be useful later and should be findable via memory search, but does not require an immediate response.
- Use `ignore_broadcast` when the content is irrelevant to the agent’s role or task and should neither clutter memory nor prompt further action.

## Notes and Limitations

- Acknowledgement only stores when the current message type is `broadcast`.
- These tools do not notify other agents and produce no user-visible output.
- If you need to respond or follow up, use `send_response` or `send_request` instead.
