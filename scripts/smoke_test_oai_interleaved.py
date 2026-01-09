# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Ryan Heaton

"""
Smoke test to investigate OAI Responses API interleaved reasoning structure.

Tests multi-turn conversation with web_search and custom tools to understand
if reasoning blocks can appear between tool calls (like Anthropic interleaved thinking).
"""

import asyncio
import json
import os

from dotenv import load_dotenv
from litellm.responses.main import aresponses
import litellm

load_dotenv()


async def test_oai_interleaved_reasoning():
    """Test OAI Responses API for interleaved reasoning between tool calls."""
    print("=" * 60)
    print("TEST: OAI Responses API - Interleaved Reasoning")
    print("=" * 60)

    litellm.drop_params = True

    tools = [
        {
            "type": "function",
            "name": "analyze_tradeoffs",
            "description": "Deeply analyze the tradeoffs between two technical approaches. You must reason carefully about pros/cons BEFORE calling this, and then reason about the results AFTER receiving them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "approach_a": {"type": "string", "description": "First approach being compared"},
                    "approach_b": {"type": "string", "description": "Second approach being compared"},
                    "context": {"type": "string", "description": "The specific use case context"},
                    "your_initial_hypothesis": {"type": "string", "description": "Your hypothesis about which is better BEFORE seeing analysis"},
                },
                "required": ["approach_a", "approach_b", "context", "your_initial_hypothesis"],
            },
        },
        {
            "type": "function",
            "name": "report_findings",
            "description": "Report your final recommendation after all analysis",
            "parameters": {
                "type": "object",
                "properties": {
                    "recommendation": {"type": "string", "description": "Your final recommendation"},
                    "reasoning_changed": {"type": "boolean", "description": "Did your thinking change after the tradeoff analysis?"},
                    "key_insight": {"type": "string", "description": "The most important insight from your research"},
                },
                "required": ["recommendation", "reasoning_changed", "key_insight"],
            },
        },
        {
            "type": "web_search",
        },
    ]

    messages = [
        {
            "role": "user",
            "content": """I need your help with a complex technical decision. Please think deeply at each step.

TASK: Help me decide between using Redis vs PostgreSQL for a job queue system.

REQUIRED STEPS (think carefully before AND after each step):
1. First, search for "Redis vs PostgreSQL job queue performance comparison 2024"
2. After reviewing search results, THINK about what you learned and form an initial hypothesis
3. Call analyze_tradeoffs with your hypothesis - be explicit about your reasoning
4. After receiving the tradeoff analysis, THINK about whether it changes your view
5. Finally, call report_findings with your recommendation

This is a critical architecture decision. Take your time to reason through each step.""",
        }
    ]

    print("\n--- Making API Call ---")
    print("Model: openai/gpt-5.2")
    print("Reasoning: enabled (effort=high, summary=detailed)")

    all_responses = []
    turn = 1

    while True:
        print(f"\n{'='*40}")
        print(f"TURN {turn}")
        print(f"{'='*40}")

        response = await aresponses(
            input=messages,
            model="openai/gpt-5.2",
            max_output_tokens=16000,
            include=["reasoning.encrypted_content"],
            reasoning={"effort": "high", "summary": "detailed"},
            tools=tools,
        )

        all_responses.append(response)

        print(f"\nResponse type: {type(response)}")
        print(f"Number of output items: {len(response.output)}")

        # Print output sequence for this turn
        print("\n--- Output Items (in order) ---")
        for i, output in enumerate(response.output):
            output_type = getattr(output, 'type', 'unknown')
            print(f"\n  Output {i}:")
            print(f"    type: {output_type}")

            if output_type == 'reasoning':
                if hasattr(output, 'summary') and output.summary:
                    summary_text = output.summary[0].text if output.summary else ""
                    print(f"    summary: {summary_text[:200]}..." if len(summary_text) > 200 else f"    summary: {summary_text}")
                else:
                    print(f"    summary: []")
            elif output_type == 'function_call':
                print(f"    name: {output.name}")
                print(f"    call_id: {output.call_id}")
                args = output.arguments if hasattr(output, 'arguments') else "{}"
                print(f"    arguments: {args[:200]}..." if len(str(args)) > 200 else f"    arguments: {args}")
            elif output_type == 'web_search_call':
                print(f"    id: {output.id}")
                print(f"    status: {getattr(output, 'status', 'N/A')}")
            elif output_type == 'message':
                content = getattr(output, 'content', [])
                if content:
                    text = content[0].text if hasattr(content[0], 'text') else str(content[0])
                    print(f"    content: {text[:200]}..." if len(text) > 200 else f"    content: {text}")

        # Print output type sequence
        print("\n--- Output Type Sequence ---")
        sequence = [getattr(o, 'type', 'unknown') for o in response.output]
        print(f"  {' -> '.join(sequence)}")

        # Check for interleaved reasoning pattern
        reasoning_indices = [i for i, o in enumerate(response.output) if getattr(o, 'type', '') == 'reasoning']
        tool_indices = [i for i, o in enumerate(response.output) if getattr(o, 'type', '') in ('function_call', 'web_search_call')]

        print(f"\n--- Interleaving Analysis ---")
        print(f"  Reasoning items at indices: {reasoning_indices}")
        print(f"  Tool items at indices: {tool_indices}")

        if len(reasoning_indices) > 1:
            print(f"  *** MULTIPLE REASONING BLOCKS DETECTED! ***")

        # Check if reasoning appears after first tool (true interleaving)
        if reasoning_indices and tool_indices:
            first_tool_idx = min(tool_indices)
            reasoning_after_tool = [r for r in reasoning_indices if r > first_tool_idx]
            if reasoning_after_tool:
                print(f"  *** REASONING AFTER TOOL CALL at indices {reasoning_after_tool}! ***")

        # Check stop reason
        stop_reason = getattr(response, 'stop_reason', None)
        print(f"\nStop reason: {stop_reason}")

        # Check if we need to handle tool results
        has_function_calls = any(getattr(o, 'type', '') == 'function_call' for o in response.output)

        if has_function_calls:
            # Collect tool results
            tool_results = []

            for output in response.output:
                if getattr(output, 'type', '') == 'function_call':
                    print(f"  -> Tool call: {output.name} (id={output.call_id[:20]}...)")

                    if output.name == "analyze_tradeoffs":
                        tool_results.append({
                            "type": "function_call_output",
                            "call_id": output.call_id,
                            "output": """TRADEOFF ANALYSIS RESULTS:

Redis Pros:
- Extremely fast in-memory operations (sub-millisecond latency)
- Built-in pub/sub for real-time job notifications
- Simple data structures perfect for queues (lists, sorted sets)
- Horizontal scaling with Redis Cluster

Redis Cons:
- Data persistence is optional/complex (RDB/AOF tradeoffs)
- Memory-bound (expensive for large job payloads)
- No built-in exactly-once delivery guarantees
- Separate infrastructure to maintain

PostgreSQL Pros:
- ACID compliance with strong durability guarantees
- SKIP LOCKED for efficient queue polling (since v9.5)
- Single database for jobs + application data
- Rich querying for job analytics/debugging
- LISTEN/NOTIFY for real-time notifications

PostgreSQL Cons:
- Higher latency than Redis (still <10ms typically)
- Table bloat requires VACUUM maintenance
- Connection pooling complexity at scale

RECOMMENDATION: For most applications, PostgreSQL with SKIP LOCKED is sufficient and simpler. Choose Redis only if you need >10k jobs/second or sub-millisecond latency.""",
                        })
                    elif output.name == "report_findings":
                        tool_results.append({
                            "type": "function_call_output",
                            "call_id": output.call_id,
                            "output": "Report recorded successfully.",
                        })

            # Build next turn input
            if tool_results:
                messages = tool_results

            turn += 1

            # Safety limit
            if turn > 10:
                print("\n[Safety limit reached - stopping]")
                break
        else:
            # No function calls or end turn
            print(f"\nConversation ended (no function calls or stop_reason={stop_reason})")
            break

    print("\n" + "=" * 60)
    print(f"CONVERSATION COMPLETE - {len(all_responses)} turns")
    print("=" * 60)

    # Analyze ALL responses for interleaving
    print("\n--- Combined Output Analysis ---")
    all_outputs = []
    for i, resp in enumerate(all_responses):
        print(f"\nTurn {i+1} outputs:")
        for output in resp.output:
            all_outputs.append((i+1, output))
            output_type = getattr(output, 'type', 'unknown')
            print(f"  {output_type}", end="")
            if output_type == 'function_call':
                print(f" ({output.name})", end="")
            print()

    print("\n--- Full Output Type Sequence (all turns) ---")
    sequence = [f"T{turn}:{getattr(o, 'type', 'unknown')}" for turn, o in all_outputs]
    print(f"  {' -> '.join(sequence)}")

    # Check for ANY interleaving across all turns
    print("\n--- Interleaving Summary ---")
    total_reasoning = sum(1 for _, o in all_outputs if getattr(o, 'type', '') == 'reasoning')
    total_tools = sum(1 for _, o in all_outputs if getattr(o, 'type', '') in ('function_call', 'web_search_call'))
    print(f"  Total reasoning blocks: {total_reasoning}")
    print(f"  Total tool calls: {total_tools}")

    # Check if multiple reasoning blocks exist within any single turn
    for i, resp in enumerate(all_responses):
        reasoning_count = sum(1 for o in resp.output if getattr(o, 'type', '') == 'reasoning')
        if reasoning_count > 1:
            print(f"  Turn {i+1}: {reasoning_count} reasoning blocks (INTERLEAVED!)")

    return all_responses


async def main():
    print("Smoke Test: OAI Responses API Interleaved Reasoning")
    print("=" * 60)
    print()

    await test_oai_interleaved_reasoning()

    print("\n" + "=" * 60)
    print("SMOKE TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
