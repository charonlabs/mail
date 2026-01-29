# Agents & Tools

## Agents
- An **agent** is an async callable created by a factory that takes a chat history and can emit tool calls ([src/mail/api.py](/src/mail/api.py), [src/mail/factories/](/src/mail/factories/__init__.py))
- Agent types can be configured in [swarms.json](/swarms.json) and converted to `MAILAgentTemplate` at runtime
- **Important flags**: `enable_entrypoint`, `enable_interswarm`, `can_complete_tasks`, `tool_format`
- Values inside `agent_params` support string prefixes resolved at load time: use `python::package.module:OBJECT` for Python exports and `url::https://...` to fetch JSON payloads that populate prompts or additional settings

## Actions
- A `MAILAction` defines a structured tool interface backed by a Python function (or coroutine)
- Author new actions with the `@mail.action` decorator or `MAILAction.from_pydantic_model()` helper in [src/mail/api.py](/src/mail/api.py)
- Declare actions once per swarm in [swarms.json](/swarms.json); agents reference them by name in their `actions` list
- Reuse shared actions via the swarm-level `action_imports` array (see [docs/stdlib](./stdlib/README.md) for the built-in catalogue)
- Conversion helpers build Pydantic models and tool specs: see `MAILAction.to_tool_dict()` and `pydantic_model_to_tool()` in [src/mail/core/tools.py](/src/mail/core/tools.py) and [src/mail/api.py](/src/mail/api.py)

## Tool format
- `tool_format` controls how tools are exposed: `completions` (chat completions) or `responses` (OpenAI Responses API shape)
- The system mirrors definitions appropriately so both shapes are supported internally

## Built-in MAIL tools ([src/mail/core/tools.py](/src/mail/core/tools.py))
- `send_request(target, subject, body)` → emits a `MAILRequest` to a validated in-swarm target; when the agent template enables interswarm the `target` accepts the `agent@swarm` form.
- `send_response(target, subject, body)` → mirrors `send_request` but produces a `MAILResponse`, letting agents continue existing conversations.
- `send_interrupt(target, subject, body)` → issues a `MAILInterrupt` so supervisors can pause or redirect downstream agents.
- `send_broadcast(subject, body, targets)` → schema includes `targets`, but the runtime currently ignores it and broadcasts to every agent in the local swarm.
- `acknowledge_broadcast(note=None)` → records the broadcast in agent memory without replying; the optional note stays internal.
- `ignore_broadcast(reason=None)` → explicitly drops the broadcast and skips both memory storage and outbound mail; optional reason is internal only.
- `await_message(reason=None)` → signals that the agent has no further output this turn and should be rescheduled when new mail arrives; an optional reason is surfaced in SSE events and tool-call history for debugging.
- `help(get_summary=True, get_identity=False, get_tool_help=None, get_full_protocol=False)` → generates a MAIL primer for the calling agent, optionally including identity info, per-tool guides, and the full protocol spec; the runtime streams the result back as a system broadcast.
- `send_interswarm_broadcast(subject, body, target_swarms=[])` → (supervisor + interswarm) sends a broadcast to selected remote swarms, defaulting to all when the list is empty.
- `discover_swarms(discovery_urls)` → (supervisor + interswarm) hands discovery endpoints to the registry so it can import additional swarms.
- `task_complete(finish_message)` → (supervisor) broadcasts the final answer and tells the runtime the task loop is finished.

`create_mail_tools()` installs the standard request/response plus broadcast acknowledgement helpers for regular agents, while `create_supervisor_tools()` layers on interrupts, broadcasts, discovery, and task completion based on the template flags described above.

## Supervisors
- Agents with `can_complete_tasks: true` can **signal task completion** and are treated as supervisors
- **Swarms must include at least one supervisor**; the default example uses `supervisor` as the entrypoint

## Communication graph
- `comm_targets` names define a directed graph of which agents an agent can contact
- When interswarm is enabled, targets may include `agent@swarm` and local validation allows remote addresses

## Factories and prompts
- **Example factories and prompts** live in [src/mail/examples/*](/src/mail/examples/__init__.py) and [src/mail/factories/*](/src/mail/factories/__init__.py)
- **Add your own agent** by creating a MAIL-compatible agent function and listing it in [swarms.json](/swarms.json)
- When referencing shared prompt text or other dynamic values, prefer the `python::` and `url::` prefixes so they stay in sync with code or remote configuration without manual duplication
