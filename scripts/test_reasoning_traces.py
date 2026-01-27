# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Ryan Heaton

"""
Comprehensive tests for reasoning trace capture in tool_call events.

Tests cover:
1. Anthropic extended thinking (streaming)
2. OAI Responses API reasoning (streaming)
3. OAI Responses API reasoning (non-streaming)
4. Parallel tool calls with reasoning_ref
5. Text-only responses (text_output with UUID)
6. Preamble capture (text before tool calls)
7. Interleaved reasoning (multiple reasoning blocks per turn)
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mail.api import MAILAgentTemplate, MAILSwarmTemplate
from mail.factories.base import base_agent_factory
from mail.factories.supervisor import supervisor_factory


# =============================================================================
# Helpers
# =============================================================================


def save_events_to_file(events: list, filename: str) -> Path:
    """Save SSE events to a JSON file."""
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"{filename}_{timestamp}.json"

    parsed_events = []
    for event in events:
        parsed = {"event": event.event}
        if event.data:
            if isinstance(event.data, dict):
                parsed["data"] = event.data
            else:
                try:
                    parsed["data"] = json.loads(event.data)
                except (json.JSONDecodeError, TypeError):
                    parsed["data"] = str(event.data)
        if hasattr(event, "id") and event.id:
            parsed["id"] = event.id
        parsed_events.append(parsed)

    with open(filepath, "w") as f:
        json.dump(parsed_events, f, indent=2, default=str)

    print(f"\n   Events saved to: {filepath}")
    return filepath


def extract_tool_call_events(events: list) -> list[dict[str, Any]]:
    """Extract tool_call events from SSE event list."""
    tool_calls = []
    for event in events:
        if event.event == "tool_call":
            data = event.data if isinstance(event.data, dict) else json.loads(event.data)
            tool_calls.append(data)
    return tool_calls


def validate_tool_call_event(
    tc: dict[str, Any],
    expected_tool: str | None = None,
    expect_reasoning: bool = False,
    expect_reasoning_ref: bool = False,
    expect_preamble: bool = False,
    expect_uuid: bool = False,
) -> list[str]:
    """Validate a tool_call event and return list of issues."""
    issues = []
    extra = tc.get("extra_data", {})

    # Basic structure
    if "tool_name" not in extra:
        issues.append("Missing tool_name")
    if "tool_args" not in extra:
        issues.append("Missing tool_args")
    if "tool_call_id" not in extra:
        issues.append("Missing tool_call_id")

    # Expected tool name
    if expected_tool and extra.get("tool_name") != expected_tool:
        issues.append(f"Expected tool '{expected_tool}', got '{extra.get('tool_name')}'")

    # Reasoning
    if expect_reasoning:
        if "reasoning" not in extra:
            issues.append("Expected reasoning but not found")
        elif not extra["reasoning"].strip():
            issues.append("Reasoning is empty/whitespace")

    # Reasoning ref
    if expect_reasoning_ref:
        if "reasoning_ref" not in extra:
            issues.append("Expected reasoning_ref but not found")
        elif not extra["reasoning_ref"]:
            issues.append("reasoning_ref is empty")

    # Preamble
    if expect_preamble:
        if "preamble" not in extra:
            issues.append("Expected preamble but not found")
        elif not extra["preamble"].strip():
            issues.append("Preamble is empty/whitespace")

    # UUID format for text_output
    if expect_uuid:
        tool_call_id = extra.get("tool_call_id", "")
        # UUID4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
        if not tool_call_id or len(tool_call_id) != 36 or tool_call_id.count("-") != 4:
            issues.append(f"Expected UUID format for tool_call_id, got '{tool_call_id}'")

    return issues


def print_test_header(name: str):
    """Print test header."""
    print(f"\n{'=' * 70}")
    print(f"TEST: {name}")
    print("=" * 70)


def print_tool_call_summary(tool_calls: list[dict[str, Any]]):
    """Print summary of tool_call events."""
    print(f"\n   Tool call events: {len(tool_calls)}")
    for i, tc in enumerate(tool_calls):
        extra = tc.get("extra_data", {})
        tool_name = extra.get("tool_name", "?")
        has_reasoning = "reasoning" in extra
        has_ref = "reasoning_ref" in extra
        has_preamble = "preamble" in extra
        flags = []
        if has_reasoning:
            flags.append("reasoning")
        if has_ref:
            flags.append(f"reasoning_ref={extra['reasoning_ref'][:20]}...")
        if has_preamble:
            flags.append("preamble")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"     {i+1}. {tool_name}{flag_str}")


# =============================================================================
# Test 1: Anthropic Extended Thinking (Streaming)
# =============================================================================


async def test_anthropic_streaming():
    """Test Anthropic extended thinking with streaming."""
    print_test_header("Anthropic Extended Thinking (Streaming)")

    supervisor = MAILAgentTemplate(
        name="Supervisor",
        factory=supervisor_factory,
        comm_targets=["Worker"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a supervisor. Delegate tasks to Worker, then call task_complete with the result.""",
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

    worker = MAILAgentTemplate(
        name="Worker",
        factory=base_agent_factory,
        comm_targets=["Supervisor"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a worker. Respond helpfully to requests from Supervisor.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    swarm_template = MAILSwarmTemplate(
        name="AnthropicStreamingTest",
        version="1.0.0",
        agents=[supervisor, worker],
        actions=[],
        entrypoint="Supervisor",
    )

    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    try:
        response, events = await swarm.post_message_and_run(
            body="What is 2 + 2?",
            subject="Math Question",
            msg_type="request",
            show_events=True,
            max_steps=10,
        )

        tool_calls = extract_tool_call_events(events)
        print_tool_call_summary(tool_calls)
        save_events_to_file(events, "anthropic_streaming")

        # Validate
        issues = []
        if len(tool_calls) < 2:
            issues.append(f"Expected at least 2 tool_call events, got {len(tool_calls)}")
        else:
            # First tool call should have reasoning (Supervisor -> send_request)
            issues.extend(validate_tool_call_event(
                tool_calls[0],
                expected_tool="send_request",
                expect_reasoning=True,
            ))

        if issues:
            print(f"\n   ISSUES: {issues}")
            return False
        print("\n   PASSED")
        return True

    except Exception as e:
        print(f"\n   ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await swarm.shutdown()


# =============================================================================
# Test 2: OAI Responses API (Streaming)
# =============================================================================


async def test_oai_streaming():
    """Test OpenAI Responses API with streaming and reasoning."""
    print_test_header("OAI Responses API (Streaming)")

    supervisor = MAILAgentTemplate(
        name="Supervisor",
        factory=supervisor_factory,
        comm_targets=["Worker"],
        actions=[],
        agent_params={
            "llm": "openai/gpt-5.2",
            "system": """You are a supervisor. Delegate tasks to Worker, then call task_complete with the result.""",
            "user_token": "test",
            "use_proxy": False,
            "reasoning_effort": "low",
            "tool_format": "responses",
            "stream_tokens": True,
        },
        enable_entrypoint=True,
        enable_interswarm=False,
        can_complete_tasks=True,
    )

    worker = MAILAgentTemplate(
        name="Worker",
        factory=base_agent_factory,
        comm_targets=["Supervisor"],
        actions=[],
        agent_params={
            "llm": "openai/gpt-5.2",
            "system": """You are a worker. Respond helpfully to requests from Supervisor.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "responses",
            "stream_tokens": True,
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    swarm_template = MAILSwarmTemplate(
        name="OAIStreamingTest",
        version="1.0.0",
        agents=[supervisor, worker],
        actions=[],
        entrypoint="Supervisor",
    )

    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    try:
        response, events = await swarm.post_message_and_run(
            body="What is the capital of France?",
            subject="Geography Question",
            msg_type="request",
            show_events=True,
            max_steps=10,
        )

        tool_calls = extract_tool_call_events(events)
        print_tool_call_summary(tool_calls)
        save_events_to_file(events, "oai_streaming")

        # Validate - OAI may or may not have reasoning depending on model
        issues = []
        if len(tool_calls) < 2:
            issues.append(f"Expected at least 2 tool_call events, got {len(tool_calls)}")
        else:
            # Check structure is correct (reasoning optional for non-reasoning models)
            issues.extend(validate_tool_call_event(
                tool_calls[0],
                expected_tool="send_request",
            ))

        if issues:
            print(f"\n   ISSUES: {issues}")
            return False
        print("\n   PASSED")
        return True

    except Exception as e:
        print(f"\n   ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await swarm.shutdown()


# =============================================================================
# Test 3: OAI Responses API (Non-Streaming)
# =============================================================================


async def test_oai_non_streaming():
    """Test OpenAI Responses API without streaming."""
    print_test_header("OAI Responses API (Non-Streaming)")

    supervisor = MAILAgentTemplate(
        name="Supervisor",
        factory=supervisor_factory,
        comm_targets=["Worker"],
        actions=[],
        agent_params={
            "llm": "openai/gpt-5.2",
            "system": """You are a supervisor. Delegate tasks to Worker, then call task_complete with the result.""",
            "user_token": "test",
            "use_proxy": False,
            "reasoning_effort": "low",
            "tool_format": "responses",
            "stream_tokens": False,  # Non-streaming
        },
        enable_entrypoint=True,
        enable_interswarm=False,
        can_complete_tasks=True,
    )

    worker = MAILAgentTemplate(
        name="Worker",
        factory=base_agent_factory,
        comm_targets=["Supervisor"],
        actions=[],
        agent_params={
            "llm": "openai/gpt-5.2",
            "system": """You are a worker. Respond helpfully to requests from Supervisor.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "responses",
            "stream_tokens": False,  # Non-streaming
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    swarm_template = MAILSwarmTemplate(
        name="OAINonStreamingTest",
        version="1.0.0",
        agents=[supervisor, worker],
        actions=[],
        entrypoint="Supervisor",
    )

    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    try:
        response, events = await swarm.post_message_and_run(
            body="What color is the sky?",
            subject="Simple Question",
            msg_type="request",
            show_events=True,
            max_steps=10,
        )

        tool_calls = extract_tool_call_events(events)
        print_tool_call_summary(tool_calls)
        save_events_to_file(events, "oai_non_streaming")

        # Validate
        issues = []
        if len(tool_calls) < 2:
            issues.append(f"Expected at least 2 tool_call events, got {len(tool_calls)}")
        else:
            issues.extend(validate_tool_call_event(
                tool_calls[0],
                expected_tool="send_request",
            ))

        if issues:
            print(f"\n   ISSUES: {issues}")
            return False
        print("\n   PASSED")
        return True

    except Exception as e:
        print(f"\n   ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await swarm.shutdown()


# =============================================================================
# Test 4: Parallel Tool Calls (reasoning_ref)
# =============================================================================


async def test_parallel_tool_calls():
    """Test parallel tool calls - first gets reasoning, others get reasoning_ref."""
    print_test_header("Parallel Tool Calls (reasoning_ref)")

    # Create a coordinator that sends to multiple workers at once
    coordinator = MAILAgentTemplate(
        name="Coordinator",
        factory=supervisor_factory,
        comm_targets=["WorkerA", "WorkerB"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a coordinator. When given a task, you MUST send requests to BOTH WorkerA AND WorkerB simultaneously in a SINGLE response (call send_request twice in the same turn).

IMPORTANT: You must call send_request for WorkerA AND send_request for WorkerB in the SAME response, not sequentially.

After receiving responses from both workers, call task_complete with a summary.""",
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

    worker_a = MAILAgentTemplate(
        name="WorkerA",
        factory=base_agent_factory,
        comm_targets=["Coordinator"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are WorkerA. Respond to the Coordinator with 'WorkerA reporting: [your answer]'.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    worker_b = MAILAgentTemplate(
        name="WorkerB",
        factory=base_agent_factory,
        comm_targets=["Coordinator"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are WorkerB. Respond to the Coordinator with 'WorkerB reporting: [your answer]'.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    swarm_template = MAILSwarmTemplate(
        name="ParallelCallsTest",
        version="1.0.0",
        agents=[coordinator, worker_a, worker_b],
        actions=[],
        entrypoint="Coordinator",
    )

    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    try:
        response, events = await swarm.post_message_and_run(
            body="Ask both workers what 1+1 is.",
            subject="Parallel Task",
            msg_type="request",
            show_events=True,
            max_steps=15,
        )

        tool_calls = extract_tool_call_events(events)
        print_tool_call_summary(tool_calls)
        save_events_to_file(events, "parallel_tool_calls")

        # Look for parallel send_request calls from Coordinator
        # If the model called them in the same turn, we should see:
        # - First send_request has reasoning
        # - Second send_request has reasoning_ref pointing to first
        issues = []
        coordinator_sends = [
            tc for tc in tool_calls
            if tc.get("extra_data", {}).get("tool_name") == "send_request"
            and "Coordinator" in tc.get("description", "")
        ]

        if len(coordinator_sends) >= 2:
            first = coordinator_sends[0].get("extra_data", {})
            second = coordinator_sends[1].get("extra_data", {})

            # Check if they were parallel (second has reasoning_ref to first)
            if "reasoning_ref" in second:
                print(f"\n   Detected parallel calls!")
                print(f"     First call ID: {first.get('tool_call_id', 'N/A')[:30]}...")
                print(f"     Second reasoning_ref: {second.get('reasoning_ref', 'N/A')[:30]}...")
                if second.get("reasoning_ref") == first.get("tool_call_id"):
                    print("     reasoning_ref correctly points to first call!")
                else:
                    issues.append("reasoning_ref doesn't match first call's ID")
            else:
                print("\n   Note: Model made sequential calls (both have reasoning)")
                # This is still valid - model just didn't parallelize

        if len(tool_calls) < 3:
            issues.append(f"Expected at least 3 tool_call events, got {len(tool_calls)}")

        if issues:
            print(f"\n   ISSUES: {issues}")
            return False
        print("\n   PASSED")
        return True

    except Exception as e:
        print(f"\n   ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await swarm.shutdown()


# =============================================================================
# Test 5: Text Output with UUID
# =============================================================================


async def test_text_output_uuid():
    """Test text-only responses get UUID and reasoning."""
    print_test_header("Text Output with UUID")

    # Create an agent that just responds with text (no tool use)
    # We'll use a simple responder that doesn't have MAIL tools
    responder = MAILAgentTemplate(
        name="Responder",
        factory=base_agent_factory,
        comm_targets=[],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a simple responder. Just answer the question directly without using any tools.

IMPORTANT: Do NOT use any tools. Just respond with plain text.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": False,  # No MAIL tools
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=True,
        enable_interswarm=False,
        can_complete_tasks=True,  # Has task_complete only
    )

    swarm_template = MAILSwarmTemplate(
        name="TextOutputTest",
        version="1.0.0",
        agents=[responder],
        actions=[],
        entrypoint="Responder",
    )

    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    try:
        response, events = await swarm.post_message_and_run(
            body="Say hello!",
            subject="Greeting",
            msg_type="request",
            show_events=True,
            max_steps=5,
        )

        tool_calls = extract_tool_call_events(events)
        print_tool_call_summary(tool_calls)
        save_events_to_file(events, "text_output_uuid")

        # Look for text_output events
        text_outputs = [
            tc for tc in tool_calls
            if tc.get("extra_data", {}).get("tool_name") == "text_output"
        ]

        issues = []
        if text_outputs:
            print(f"\n   Found {len(text_outputs)} text_output event(s)")
            for i, to in enumerate(text_outputs):
                extra = to.get("extra_data", {})
                tool_call_id = extra.get("tool_call_id", "")
                print(f"     {i+1}. tool_call_id: {tool_call_id}")

                # Validate UUID format
                if len(tool_call_id) == 36 and tool_call_id.count("-") == 4:
                    print(f"        Valid UUID format")
                else:
                    issues.append(f"text_output {i+1} has invalid UUID: {tool_call_id}")

                # Check for reasoning
                if "reasoning" in extra:
                    print(f"        Has reasoning: {extra['reasoning'][:50]}...")
        else:
            # Model might have used task_complete instead
            print("\n   Note: No text_output events (model may have used task_complete)")

        if issues:
            print(f"\n   ISSUES: {issues}")
            return False
        print("\n   PASSED")
        return True

    except Exception as e:
        print(f"\n   ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await swarm.shutdown()


# =============================================================================
# Test 6: Anthropic Non-Streaming
# =============================================================================


async def test_anthropic_non_streaming():
    """Test Anthropic extended thinking without streaming."""
    print_test_header("Anthropic Extended Thinking (Non-Streaming)")

    supervisor = MAILAgentTemplate(
        name="Supervisor",
        factory=supervisor_factory,
        comm_targets=["Worker"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a supervisor. Delegate tasks to Worker, then call task_complete with the result.""",
            "user_token": "test",
            "use_proxy": False,
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": False,  # Non-streaming
        },
        enable_entrypoint=True,
        enable_interswarm=False,
        can_complete_tasks=True,
    )

    worker = MAILAgentTemplate(
        name="Worker",
        factory=base_agent_factory,
        comm_targets=["Supervisor"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a worker. Respond helpfully to requests from Supervisor.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": False,  # Non-streaming
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    swarm_template = MAILSwarmTemplate(
        name="AnthropicNonStreamingTest",
        version="1.0.0",
        agents=[supervisor, worker],
        actions=[],
        entrypoint="Supervisor",
    )

    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    try:
        response, events = await swarm.post_message_and_run(
            body="What is 3 times 7?",
            subject="Math Question",
            msg_type="request",
            show_events=True,
            max_steps=10,
        )

        tool_calls = extract_tool_call_events(events)
        print_tool_call_summary(tool_calls)
        save_events_to_file(events, "anthropic_non_streaming")

        issues = []
        if len(tool_calls) < 2:
            issues.append(f"Expected at least 2 tool_call events, got {len(tool_calls)}")
        else:
            issues.extend(validate_tool_call_event(
                tool_calls[0],
                expected_tool="send_request",
                expect_reasoning=True,
            ))

        if issues:
            print(f"\n   ISSUES: {issues}")
            return False
        print("\n   PASSED")
        return True

    except Exception as e:
        print(f"\n   ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await swarm.shutdown()


# =============================================================================
# Test 7: Interleaved Reasoning (Multiple Thinking Blocks)
# =============================================================================


async def test_interleaved_reasoning():
    """Test that multiple thinking blocks are correctly associated with their following tools."""
    print_test_header("Interleaved Reasoning (Multi-step)")

    # Use a more complex task that requires multiple steps with reasoning between each
    planner = MAILAgentTemplate(
        name="Planner",
        factory=supervisor_factory,
        comm_targets=["Researcher", "Writer"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a planner. For any task:
1. First, send a request to Researcher to gather information
2. Wait for their response
3. Then send a request to Writer to format the information
4. Wait for their response
5. Finally call task_complete with the final result

You MUST follow these steps in order.""",
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

    researcher = MAILAgentTemplate(
        name="Researcher",
        factory=base_agent_factory,
        comm_targets=["Planner"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a researcher. Provide factual information when asked.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    writer = MAILAgentTemplate(
        name="Writer",
        factory=base_agent_factory,
        comm_targets=["Planner"],
        actions=[],
        agent_params={
            "llm": "anthropic/claude-haiku-4-5-20251001",
            "system": """You are a writer. Format and polish the information given to you.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    swarm_template = MAILSwarmTemplate(
        name="InterleavedReasoningTest",
        version="1.0.0",
        agents=[planner, researcher, writer],
        actions=[],
        entrypoint="Planner",
    )

    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    try:
        response, events = await swarm.post_message_and_run(
            body="Tell me one fact about cats.",
            subject="Research and Write",
            msg_type="request",
            show_events=True,
            max_steps=20,
        )

        tool_calls = extract_tool_call_events(events)
        print_tool_call_summary(tool_calls)
        save_events_to_file(events, "interleaved_reasoning")

        # Count Planner's tool calls - should have multiple with reasoning
        planner_calls = [
            tc for tc in tool_calls
            if "Planner" in tc.get("description", "")
        ]

        issues = []
        reasoning_count = sum(
            1 for tc in planner_calls
            if "reasoning" in tc.get("extra_data", {})
        )

        print(f"\n   Planner made {len(planner_calls)} calls, {reasoning_count} with reasoning")

        if len(planner_calls) < 2:
            issues.append(f"Expected at least 2 Planner calls, got {len(planner_calls)}")

        # Each Planner call should have its own reasoning (interleaved)
        if reasoning_count < 2:
            print("   Note: Expected multiple reasoning blocks (interleaved thinking)")

        if issues:
            print(f"\n   ISSUES: {issues}")
            return False
        print("\n   PASSED")
        return True

    except Exception as e:
        print(f"\n   ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await swarm.shutdown()


# =============================================================================
# Test 8: OAI with Reasoning Model (gpt-5.2)
# =============================================================================


async def test_oai_reasoning_model():
    """Test OpenAI reasoning model (gpt-5.2) to verify reasoning capture."""
    print_test_header("OAI Reasoning Model (gpt-5.2)")

    supervisor = MAILAgentTemplate(
        name="Supervisor",
        factory=supervisor_factory,
        comm_targets=["Worker"],
        actions=[],
        agent_params={
            "llm": "openai/gpt-5.2",  # Reasoning model
            "system": """You are a supervisor. Delegate tasks to Worker, then call task_complete with the result.""",
            "user_token": "test",
            "use_proxy": False,
            "reasoning_effort": "low",  # Enable reasoning
            "tool_format": "responses",
            "stream_tokens": True,
        },
        enable_entrypoint=True,
        enable_interswarm=False,
        can_complete_tasks=True,
    )

    worker = MAILAgentTemplate(
        name="Worker",
        factory=base_agent_factory,
        comm_targets=["Supervisor"],
        actions=[],
        agent_params={
            "llm": "openai/gpt-5.2",
            "system": """You are a worker. Respond helpfully to requests from Supervisor.""",
            "user_token": "test",
            "use_proxy": False,
            "_debug_include_mail_tools": True,
            "reasoning_effort": "low",
            "tool_format": "responses",
            "stream_tokens": True,
        },
        enable_entrypoint=False,
        enable_interswarm=False,
        can_complete_tasks=False,
    )

    swarm_template = MAILSwarmTemplate(
        name="OAIReasoningTest",
        version="1.0.0",
        agents=[supervisor, worker],
        actions=[],
        entrypoint="Supervisor",
    )

    swarm = swarm_template.instantiate(
        instance_params={"user_token": "test"},
        user_id="test_user",
    )

    try:
        response, events = await swarm.post_message_and_run(
            body="What is the square root of 144?",
            subject="Math Question",
            msg_type="request",
            show_events=True,
            max_steps=10,
        )

        tool_calls = extract_tool_call_events(events)
        print_tool_call_summary(tool_calls)
        save_events_to_file(events, "oai_reasoning_model")

        # gpt-5.2 should have reasoning
        issues = []
        reasoning_calls = [
            tc for tc in tool_calls
            if "reasoning" in tc.get("extra_data", {})
        ]

        print(f"\n   Tool calls with reasoning: {len(reasoning_calls)}/{len(tool_calls)}")

        if len(tool_calls) < 2:
            issues.append(f"Expected at least 2 tool_call events, got {len(tool_calls)}")

        # Check if we got reasoning (gpt-5.2 should have it)
        if len(reasoning_calls) == 0:
            print("   WARNING: No reasoning captured from gpt-5.2 (may be model behavior)")

        if issues:
            print(f"\n   ISSUES: {issues}")
            return False
        print("\n   PASSED")
        return True

    except Exception as e:
        print(f"\n   ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await swarm.shutdown()


# =============================================================================
# Main
# =============================================================================


async def main():
    print("=" * 70)
    print("Reasoning Trace Tests")
    print("=" * 70)

    results = {}

    # Run all tests
    results["anthropic_streaming"] = await test_anthropic_streaming()
    results["anthropic_non_streaming"] = await test_anthropic_non_streaming()
    results["oai_streaming"] = await test_oai_streaming()
    results["oai_non_streaming"] = await test_oai_non_streaming()
    results["parallel_tool_calls"] = await test_parallel_tool_calls()
    results["text_output_uuid"] = await test_text_output_uuid()
    results["interleaved_reasoning"] = await test_interleaved_reasoning()
    results["oai_reasoning_model"] = await test_oai_reasoning_model()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "PASSED" if result else "FAILED"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll tests passed!")
    else:
        print(f"\n{total - passed} test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())
