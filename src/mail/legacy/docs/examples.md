# Examples

This archived v1 documentation describes example agents retained under `src/mail/legacy`. Historical root demo scripts were removed during the v2 cleanup.

## Agents
- **Supervisor**: [src/mail/legacy/examples/supervisor/](/src/mail/legacy/examples/supervisor/__init__.py)
- **Weather**: [src/mail/legacy/examples/weather_dummy/](/src/mail/legacy/examples/weather_dummy/__init__.py)
- **Math**: [src/mail/legacy/examples/math_dummy/](/src/mail/legacy/examples/math_dummy/__init__.py)
- **Consultant**: [src/mail/legacy/examples/consultant_dummy/](/src/mail/legacy/examples/consultant_dummy/__init__.py)
- **Analyst**: [src/mail/legacy/examples/analyst_dummy/](/src/mail/legacy/examples/analyst_dummy/__init__.py)

## Agent functions and factories
- **Agent factories** in [src/mail/legacy/factories/](/src/mail/legacy/factories/__init__.py) are classes/functions that construct MAIL-compatible agent callables used by `MAILAgentTemplate`.
- For class-based factories (e.g., `LiteLLMAgentFunction`), the instantiated object's `__call__` method is the agent function the runtime schedules.

## Demo scripts

The old root-level v1 demo scripts were removed during the v2 repository cleanup.
Use the retained example agents above or the archived legacy tests when checking
v1 behavior.

## Swarms configuration
- Archived [configs/swarms.json](/src/mail/legacy/configs/swarms.json) provides legacy swarm templates
- Update agent factories, prompts, or actions to customize behavior
