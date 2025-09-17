# Agents & Tools

## Agents
- An **agent** is an async callable created by a factory that takes a chat history and can emit tool calls ([src/mail/api.py](/src/mail/api.py), [src/mail/factories/](/src/mail/factories/__init__.py))
- Agent types can be configured in [swarms.json](/swarms.json) and converted to `MAILAgentTemplate` at runtime
- Important flags: `enable_entrypoint`, `enable_interswarm`, `can_complete_tasks`, `tool_format`

## Actions
- A `MAILAction` defines a structured tool interface backed by a Python function (import string)
- Actions can be attached to agents in [swarms.json](/swarms.json) and are available to the agent as OpenAI-style function tools
- Conversion helpers build Pydantic models and tool specs: see `MAILAction.to_tool_dict()` and `pydantic_model_to_tool()` in [src/mail/core/tools.py](/src/mail/core/tools.py) and [src/mail/api.py](/src/mail/api.py)

## Tool format
- `tool_format` controls how tools are exposed: `completions` (chat completions) or `responses` (OpenAI Responses API shape)
- The system mirrors definitions appropriately so both shapes are supported internally

## Built-in MAIL tools ([src/mail/core/tools.py](/src/mail/core/tools.py))
- `send_request(target, subject, message)` → emits a `MAILRequest`
- `send_response(target, subject, message)` → emits a `MAILResponse`
- `send_interrupt(target, subject, message)` → emits a `MAILInterrupt`
- `send_broadcast(subject, message)` → emits a `MAILBroadcast` to all
- `acknowledge_broadcast(note?)` → store broadcast in memory, no outgoing message
- `ignore_broadcast(reason?)` → ignore broadcast; no memory, no outgoing message
- Supervisor extras: `task_complete(finish_message)`; interswarm extras: `send_interswarm_broadcast`, `discover_swarms`

## Supervisors
- Agents with `can_complete_tasks: true` can signal task completion and are treated as supervisors
- Swarms must include at least one supervisor; the default example uses `supervisor` as the entrypoint

## Communication graph
- `comm_targets` names define a directed graph of which agents an agent can contact
- When interswarm is enabled, targets may include `agent@swarm` and local validation allows remote addresses

## Factories and prompts
- Example factories and prompts live in [src/mail/examples/*](/src/mail/examples/__init__.py) and [src/mail/factories/*](/src/mail/factories/__init__.py)
- Add your own agent by creating a factory function and listing it in [swarms.json](/swarms.json)

