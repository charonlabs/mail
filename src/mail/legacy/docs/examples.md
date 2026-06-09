# Examples

This repo includes example agents and demo scripts you can run locally.

## Agents
- **Supervisor**: [src/mail/examples/supervisor/](/src/mail/examples/supervisor/__init__.py)
- **Weather**: [src/mail/examples/weather_dummy/](/src/mail/examples/weather_dummy/__init__.py)
- **Math**: [src/mail/examples/math_dummy/](/src/mail/examples/math_dummy/__init__.py)
- **Consultant**: [src/mail/examples/consultant_dummy/](/src/mail/examples/consultant_dummy/__init__.py)
- **Analyst**: [src/mail/examples/analyst_dummy/](/src/mail/examples/analyst_dummy/__init__.py)

## Agent functions and factories
- **Agent factories** in [src/mail/factories/](/src/mail/factories/__init__.py) are classes/functions that construct MAIL-compatible agent callables used by `MAILAgentTemplate`.
- For class-based factories (e.g., `LiteLLMAgentFunction`), the instantiated object's `__call__` method is the agent function the runtime schedules.

## Demo scripts
- **Single swarm**: [scripts/single_swarm_demo.py](/scripts/single_swarm_demo.py)
- **Multiple swarms**: [scripts/multi_swarm_demo.py](/scripts/multi_swarm_demo.py)
- **HTTP client**: [scripts/demo_client.py](/scripts/demo_client.py) launches a stub server and exercises [`MAILClient`](./client.md)

## Swarms configuration
- Top-level [swarms.json](/swarms.json) provides the default template loaded by the server
- Update agent factories, prompts, or actions to customize behavior
