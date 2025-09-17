# Examples

This repo includes example agents and demo scripts you can run locally.

Agents
- Supervisor: src/mail/examples/supervisor/
- Weather: src/mail/examples/weather_dummy/
- Math: src/mail/examples/math_dummy/
- Consultant/Analyst: src/mail/examples/consultant_dummy/, src/mail/examples/analyst_dummy/

Factories
- Factory functions in src/mail/factories/ build agent callables used by MAILAgentTemplate

Demo scripts
- Single swarm: scripts/single_swarm_demo.py
- Multiple swarms: scripts/multi_swarm_demo.py

Swarms configuration
- Top-level swarms.json provides the default template loaded by the server
- Update agent factories, prompts, or actions to customize behavior

