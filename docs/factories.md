# MAIL Factories

MAIL factories encapsulate the boilerplate required to build agent callables that the runtime can schedule. They translate agent configuration—model selection, tool access, routing flags—into an async callable that conforms to `mail.core.agents.AgentFunction`.

Factories live under `src/mail/factories/` and are organized by concern:

- `base.py` provides the shared factory base classes and the `base_agent_factory` convenience function (now deprecated).
- `action.py` layers action-specific validation (e.g., pydantic tool schemas).
- `supervisor.py` wires in supervisor-only tools and policies.
- `mail.examples/*/agent.py` demonstrates how to compose these factories for concrete agents.

## Quick Start

LLM agents can be easily built with the `LiteLLMAgentFunction`. `LiteLLMAgentFunction.__init__` corresponds to the agent factory; `LiteLLMAgentFunction.__call__` represents the agent function itelf. This class wires the given tools and LiteLLM configuration into a coroutine that the runtime can invoke:

```python
from mail.factories import LiteLLMAgentFunction

analytics_agent = LiteLLMAgentFunction(
    # top-level wiring
    name="analyst",
    comm_targets=["consultant", "supervisor"],
    tools=[{"type": "function", "function": {"name": "fetch_report", "description": "...", "parameters": {...}}}],
    # LiteLLM config
    llm="openai/gpt-5-mini",
    system="system prompt string",
    tool_format="responses",
    enable_entrypoint=False,
    enable_interswarm=False,
    can_complete_tasks=False,
    # runtime instance parameter defaults
    user_token="",  # provided when instantiating a swarm (per runtime instance)
    reasoning_effort="low",
    thinking_budget=4000,
    max_tokens=6000,
    memory=True,
    use_proxy=True,
)
```

At runtime, `LiteLLMAgentFunction` receives `messages` and an optional `tool_choice`; the `user_token` is captured at instantiation time (per runtime instance), not per message.

The agent shown above can be directly run as follows:

```python
messages: list[dict[str, Any]] = [
    {
        "role": "user",
        "content": "Test message"
    }
]

tool_choice: str | dict[str, str] = "auto"

agent_output = await analytics_agent(
    messages=messages,
    tool_choice=tool_choice, # default = "required"
)
```

## Agent Function Class Hierarchy

When you need specialized behavior, inherit from the agent function classes defined in `src/mail/factories/base.py`:

- **`MAILAgentFunction`** — abstract base storing common configuration (communication targets, tool sets, scheduling flags).
- **`LiteLLMAgentFunction`** — concrete implementation that prepares LiteLLM requests for either `completions` or `responses` tool formats.

From these, `action.py` and `supervisor.py` define more specific flavors:

- **`ActionAgentFunction` / `LiteLLMActionAgentFunction`** — validate and normalize action tool schemas before delegating to LiteLLM.
- **`SupervisorFunction` / `LiteLLMSupervisorFunction`** — append supervisor control tools (`task_complete`, broadcast helpers) and enable task completion.

Extending an agent function lets you share configuration defaults while allowing callers to override instance-level settings. For example, the sample analyst agent exposes additional metadata but ultimately delegates to `LiteLLMAgentFunction`:

```python
from collections.abc import Awaitable
from typing import Any

from mail.core.tools import AgentToolCall
from mail.factories.base import LiteLLMAgentFunction


class LiteLLMAnalystFunction(LiteLLMAgentFunction):
    def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str | dict[str, str] = "required",
    ) -> Awaitable[tuple[str | None, list[AgentToolCall]]]:
        # Leverage LiteLLMAgentFunction's async implementation
        return super().__call__(messages, tool_choice)
```

This pattern keeps all LiteLLM handling inside the shared implementation while leaving room to hook custom behavior if needed (e.g., adding traces, rewriting messages).

## Tool Handling

Factories rely on utilities in `mail.core.tools` to expose MAIL-native tools and normalize user-provided actions:

- `create_mail_tools(...)` returns runtime utilities (send, ack, task_complete) and respects the `exclude_tools` list.
- `pydantic_function_tool` and `_make_tools` ensure OpenAI-style tool definitions match LiteLLM expectations.
- Supervisor factories append additional control tools via `create_supervisor_tools`.

When building custom agent functions, consider reusing these helpers instead of reimplementing tool coercion logic. That keeps behavior consistent across agents and ensures new dispatcher features (like inter-swarm messaging) propagate automatically.

## Instance Parameters vs. Top-Level Wiring

Factory call signatures follow a convention:

- **Top-level parameters** (`comm_targets`, `tools`, `name`, `enable_entrypoint`, etc.) describe the agent's static wiring and are typically supplied from `swarms.json` or other configuration.
- **Instance parameters** (`user_token`, instance-level overrides) are filled when the swarm or agent instance is created.
- **Internal parameters (`agent_params`)** (`llm`, `system`, `reasoning_effort`, `thinking_budget`) control the LLM call and are often set by package defaults or environment configuration.

`LiteLLMAgentFunction` closes over the supplied top-level settings and uses the instance parameters provided when the swarm is instantiated (for example, a per-user `user_token`).

## Integrating with Swarms

Agent definitions in `swarms.json` reference factories via import strings, for example:

```json
{
  "name": "analyst",
  "factory": "python::mail.examples.analyst_dummy.agent:LiteLLMAnalystFunction",
  "comm_targets": ["consultant", "supervisor"],
  "agent_params": {
    "llm": "openai/gpt-5-mini",
    "system": "mail.examples.analyst_dummy.prompts:SYSPROMPT"
  }
}
```

The runtime instantiates these factories through `mail.api.MAILAgentTemplate`, passing shared top-level configuration. Custom agent functions should maintain function signatures compatible with the templates so they can be plugged into swarms without additional glue code.

## Testing and Validation

- Use `uv run pytest -q` (or the scoped `tests/unit`) to exercise factory behavior. The sample agents demonstrate how to cover agent execution paths.
- Run `uv run ruff check .` and `uv run mypy src/mail` to keep style and types aligned with project standards.
- When factories introduce new tool schemas, update JSON schema fixtures under `spec/` and validate with `uv run spec/validate_samples.py`.

Keeping agent functions small and composable makes it easy to add new agent personas or capabilities without duplicating LiteLLM interaction logic. Start with `LiteLLMAgentFunction`, and lean on the shared utilities to stay consistent with the rest of MAIL.
