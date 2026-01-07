# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Ryan Heaton

"""
Smoke test for native Anthropic SDK with a real MAIL swarm.

Tests multi-turn tool use and message conversion in a real agent-to-agent
communication scenario.
"""

import asyncio

from mail.api import MAILAgentTemplate, MAILSwarmTemplate
from mail.factories.base import base_agent_factory
from mail.factories.supervisor import supervisor_factory


def create_researcher_template() -> MAILAgentTemplate:
    """Create a researcher agent that can answer questions."""
    return MAILAgentTemplate(
        name="Researcher",
        factory=base_agent_factory,
        comm_targets=["Supervisor"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a research assistant. When you receive a request from the Supervisor,
provide a helpful, detailed response based on your knowledge.

Keep responses concise but informative. Always respond to the Supervisor when asked.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",  # Enable extended thinking
            "tool_format": "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )


def create_supervisor_template() -> MAILAgentTemplate:
    """Create a supervisor agent that delegates to the researcher."""
    return MAILAgentTemplate(
        name="Supervisor",
        factory=supervisor_factory,
        comm_targets=["Researcher"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a supervisor agent. When you receive a task from the user,
delegate it to the Researcher agent by sending them a request.

Once you receive the Researcher's response, use task_complete to finish the task and provide the answer to the user.

Steps:
1. Send a request to Researcher with the user's question
2. Wait for their response
3. Call task_complete with the final answer - this is REQUIRED to end the task""",
            "user_token": "test",
            "use_proxy": False,
            "reasoning_effort": "low",  # Enable extended thinking
            "tool_format": "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=True,
        enable_interswarm=False,
        can_complete_tasks=True,
    )


async def test_swarm_communication():
    """Test real swarm with multi-turn agent communication."""
    print("=" * 60)
    print("TEST: Real MAIL Swarm with Native Anthropic SDK")
    print("=" * 60)

    # Create agent templates
    supervisor = create_supervisor_template()
    researcher = create_researcher_template()

    # Create swarm template
    swarm_template = MAILSwarmTemplate(
        name="TestSwarm",
        version="1.0.0",
        agents=[supervisor, researcher],
        actions=[],
        entrypoint="Supervisor",
        enable_interswarm=False,
        breakpoint_tools=[],
    )

    # Instantiate the swarm
    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    print("\nSwarm created with agents:")
    for agent in swarm.agents:
        print(f"  - {agent.name} (entrypoint={agent.enable_entrypoint}, supervisor={agent.can_complete_tasks})")

    print("\n" + "-" * 60)
    print("Posting message to swarm...")
    print("-" * 60)

    try:
        # Post a message and run until completion
        response, events = await swarm.post_message_and_run(
            body="What are three interesting facts about the Python programming language?",
            subject="Research Request",
            msg_type="request",
            show_events=True,
            max_steps=20,
        )

        print("\n" + "=" * 60)
        print("RESPONSE")
        print("=" * 60)

        # Extract the response body
        if "message" in response:
            msg = response["message"]
            body = msg.get("body", "")
            print(f"\nFinal response:\n{body[:1000]}...")

        print(f"\nTotal events: {len(events)}")

        # Count agent steps
        agent_steps = {}
        for event in events:
            if hasattr(event, 'data') and event.data:
                try:
                    import json
                    data = json.loads(event.data)
                    if "agent" in data:
                        agent = data["agent"]
                        agent_steps[agent] = agent_steps.get(agent, 0) + 1
                except:
                    pass

        if agent_steps:
            print("\nAgent activity:")
            for agent, count in agent_steps.items():
                print(f"  - {agent}: {count} steps")

        print("\n✅ Swarm test passed!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await swarm.shutdown()


async def test_swarm_with_web_search():
    """Test swarm with web_search tool."""
    print("\n" + "=" * 60)
    print("TEST: MAIL Swarm with web_search Tool")
    print("=" * 60)

    # Create a researcher with web_search capability
    researcher = MAILAgentTemplate(
        name="WebResearcher",
        factory=base_agent_factory,
        comm_targets=["Supervisor"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a web research assistant. Use your web search capability
to find current information when asked.

Always search the web for current/real-time information requests.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": True,
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 3,
                }
            ],
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    supervisor = MAILAgentTemplate(
        name="Supervisor",
        factory=supervisor_factory,
        comm_targets=["WebResearcher"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a supervisor. Delegate research tasks to WebResearcher.
Once you get a response, call task_complete with the final answer to finish the task.""",
            "user_token": "test",
            "use_proxy": False,
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=True,
        enable_interswarm=False,
        can_complete_tasks=True,
    )

    swarm_template = MAILSwarmTemplate(
        name="WebSearchSwarm",
        version="1.0.0",
        agents=[supervisor, researcher],
        actions=[],
        entrypoint="Supervisor",
    )

    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    print("\nSwarm created with web_search capability")
    print("-" * 60)

    try:
        response, events = await swarm.post_message_and_run(
            body="What is the current weather in Tokyo?",
            subject="Weather Request",
            msg_type="request",
            show_events=True,
            max_steps=20,
        )

        print("\n" + "=" * 60)
        print("RESPONSE")
        print("=" * 60)

        if "message" in response:
            msg = response["message"]
            body = msg.get("body", "")
            print(f"\nFinal response:\n{body[:1000]}...")

        print(f"\nTotal events: {len(events)}")
        print("\n✅ Web search swarm test passed!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await swarm.shutdown()


async def main():
    print("=" * 60)
    print("Smoke Tests: Native Anthropic SDK with Real MAIL Swarm")
    print("=" * 60)
    print()

    await test_swarm_communication()
    await test_swarm_with_web_search()

    print("\n" + "=" * 60)
    print("ALL SWARM TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
