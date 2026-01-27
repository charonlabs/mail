# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Ryan Heaton

"""
Smoke test to investigate Anthropic extended thinking block structure.

Tests interleaved thinking with tool calls to understand block ordering
and different block types (thinking, redacted_thinking, tool_use, server_tool_use, text).
"""

import asyncio
import json
import os

from dotenv import load_dotenv
import anthropic

load_dotenv()


async def test_anthropic_thinking_with_tools():
    """Test Anthropic extended thinking with tool calls."""
    print("=" * 60)
    print("TEST: Anthropic Extended Thinking with Tools")
    print("=" * 60)

    client = anthropic.AsyncAnthropic()

    messages = [
        {
            "role": "user",
            "content": """I need you to do two things:
1. First, search the web for "current weather in Tokyo"
2. Then, call the report_findings tool with what you learned

Think carefully about each step before acting.""",
        }
    ]

    tools = [
        {
            "name": "report_findings",
            "description": "Report your findings from the research",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Summary of findings"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["summary", "confidence"],
            },
        },
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        },
    ]

    print("\n--- Making API Call ---")
    print("Model: claude-sonnet-4-20250514")
    print("Extended thinking: enabled (budget=5000)")

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        thinking={
            "type": "enabled",
            "budget_tokens": 5000,
        },
        tools=tools,
        messages=messages,
    )

    print("\n--- Response Structure ---")
    print(f"Stop reason: {response.stop_reason}")
    print(f"Number of content blocks: {len(response.content)}")

    print("\n--- Content Blocks (in order) ---")
    for i, block in enumerate(response.content):
        print(f"\n  Block {i}:")
        print(f"    type: {block.type}")

        if block.type == "thinking":
            print(f"    thinking: {block.thinking[:200]}..." if len(block.thinking) > 200 else f"    thinking: {block.thinking}")
            if hasattr(block, "signature"):
                print(f"    signature: {block.signature[:50]}...")
        elif block.type == "redacted_thinking":
            print(f"    data: [REDACTED - {len(block.data) if hasattr(block, 'data') else 'N/A'} chars]")
        elif block.type == "tool_use":
            print(f"    id: {block.id}")
            print(f"    name: {block.name}")
            print(f"    input: {json.dumps(block.input)[:200]}")
        elif block.type == "server_tool_use":
            print(f"    id: {block.id}")
            print(f"    name: {block.name}")
            if hasattr(block, "input"):
                print(f"    input: {block.input}")
        elif block.type == "text":
            print(f"    text: {block.text[:200]}..." if len(block.text) > 200 else f"    text: {block.text}")

    print("\n--- Block Type Sequence ---")
    sequence = [block.type for block in response.content]
    print(f"  {' -> '.join(sequence)}")

    print("\n--- Raw Response (model_dump) ---")
    try:
        dump = response.model_dump()
        print(json.dumps(dump, indent=2, default=str)[:3000])
        if len(json.dumps(dump, default=str)) > 3000:
            print("... [truncated]")
    except Exception as e:
        print(f"  ERROR: {e}")

    return response


async def test_anthropic_thinking_text_only():
    """Test Anthropic extended thinking with text-only response (no tools)."""
    print("\n" + "=" * 60)
    print("TEST: Anthropic Extended Thinking - Text Only Response")
    print("=" * 60)

    client = anthropic.AsyncAnthropic()

    messages = [
        {
            "role": "user",
            "content": """Solve this logic puzzle and explain your reasoning:

Three logicians walk into a bar. The bartender asks "Does everyone want a drink?"
The first logician says "I don't know."
The second logician says "I don't know."
The third logician says "Yes."

Why could the third logician answer definitively?""",
        }
    ]

    print("\n--- Making API Call (no tools) ---")
    print("Model: claude-sonnet-4-20250514")
    print("Extended thinking: enabled (budget=5000)")

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        thinking={
            "type": "enabled",
            "budget_tokens": 5000,
        },
        messages=messages,
    )

    print("\n--- Response Structure ---")
    print(f"Stop reason: {response.stop_reason}")
    print(f"Number of content blocks: {len(response.content)}")

    print("\n--- Content Blocks (in order) ---")
    for i, block in enumerate(response.content):
        print(f"\n  Block {i}:")
        print(f"    type: {block.type}")

        if block.type == "thinking":
            print(f"    thinking: {block.thinking[:300]}..." if len(block.thinking) > 300 else f"    thinking: {block.thinking}")
        elif block.type == "redacted_thinking":
            print(f"    data: [REDACTED]")
        elif block.type == "text":
            print(f"    text: {block.text[:300]}..." if len(block.text) > 300 else f"    text: {block.text}")

    print("\n--- Block Type Sequence ---")
    sequence = [block.type for block in response.content]
    print(f"  {' -> '.join(sequence)}")

    return response


async def test_anthropic_interleaved_thinking():
    """Test interleaved thinking pattern: think -> tool -> think -> tool."""
    print("\n" + "=" * 60)
    print("TEST: Anthropic Interleaved Thinking (with server_tool_use)")
    print("=" * 60)

    client = anthropic.AsyncAnthropic()

    tools = [
        {
            "name": "analyze_tradeoffs",
            "description": "Deeply analyze the tradeoffs between two technical approaches. You must reason carefully about pros/cons BEFORE calling this, and then reason about the results AFTER receiving them.",
            "input_schema": {
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
            "name": "report_findings",
            "description": "Report your final recommendation after all analysis",
            "input_schema": {
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
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 5,
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
    print("Model: claude-sonnet-4-5-20250929")
    print("Extended thinking: enabled (budget=10000)")

    all_responses = []
    turn = 1

    while True:
        print(f"\n{'='*40}")
        print(f"TURN {turn}")
        print(f"{'='*40}")

        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": 10000,
            },
            tools=tools,
            messages=messages,
            extra_headers={
                "anthropic-beta": "interleaved-thinking-2025-05-14"
            },
        )

        all_responses.append(response)

        print(f"\nStop reason: {response.stop_reason}")
        print(f"Number of content blocks: {len(response.content)}")

        # Print block sequence for this turn
        sequence = [block.type for block in response.content]
        print(f"Block sequence: {' -> '.join(sequence)}")

        # Check if we need to handle tool results
        if response.stop_reason == "tool_use":
            # Collect tool results
            tool_results = []
            assistant_content = []

            for block in response.content:
                # Keep all blocks for assistant message
                if block.type == "thinking":
                    assistant_content.append({
                        "type": "thinking",
                        "thinking": block.thinking,
                        "signature": block.signature,
                    })
                elif block.type == "redacted_thinking":
                    assistant_content.append({
                        "type": "redacted_thinking",
                        "data": block.data,
                    })
                elif block.type == "text":
                    assistant_content.append({
                        "type": "text",
                        "text": block.text,
                    })
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    # Create dummy result for client-side tools
                    print(f"  -> Tool call: {block.name} (id={block.id[:20]}...)")
                    if block.name == "analyze_tradeoffs":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": """TRADEOFF ANALYSIS RESULTS:

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
                    elif block.name == "report_findings":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Report recorded successfully.",
                        })
                elif block.type == "server_tool_use":
                    # Server tool use - include as-is
                    assistant_content.append(block.model_dump())
                    print(f"  -> Server tool: {block.name} (id={block.id[:20]}...)")
                else:
                    # Any other block type (server results, etc) - include as-is
                    assistant_content.append(block.model_dump())
                    print(f"  -> Other block: {block.type}")

            # Add assistant message with all content
            messages.append({"role": "assistant", "content": assistant_content})

            # Add tool results if any client-side tools were called
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            turn += 1

            # Safety limit
            if turn > 10:
                print("\n[Safety limit reached - stopping]")
                break
        else:
            # End turn or other stop reason
            print(f"\nConversation ended with stop_reason: {response.stop_reason}")
            break

    print("\n" + "=" * 60)
    print(f"CONVERSATION COMPLETE - {len(all_responses)} turns")
    print("=" * 60)

    # Now analyze ALL responses
    print("\n--- Combined Block Analysis ---")
    all_blocks = []
    for i, resp in enumerate(all_responses):
        print(f"\nTurn {i+1} blocks:")
        for block in resp.content:
            all_blocks.append((i+1, block))
            print(f"  {block.type}", end="")
            if block.type in ("tool_use", "server_tool_use"):
                print(f" ({block.name})", end="")
            print()

    print("\n--- Full Block Type Sequence (all turns) ---")
    sequence = [f"T{turn}:{block.type}" for turn, block in all_blocks]
    print(f"  {' -> '.join(sequence)}")

    # Analyze interleaving pattern across ALL turns
    print("\n--- Interleaving Analysis (All Turns) ---")
    thinking_to_tool = []

    for turn_idx, resp in enumerate(all_responses):
        current_thinking = []
        current_thinking_content = []

        for block in resp.content:
            if block.type == "thinking":
                current_thinking.append(block.type)
                thinking_text = block.thinking[:100] + "..." if len(block.thinking) > 100 else block.thinking
                current_thinking_content.append(thinking_text)
            elif block.type == "redacted_thinking":
                current_thinking.append(block.type)
                current_thinking_content.append("[REDACTED]")
            elif block.type in ("tool_use", "server_tool_use"):
                tool_input = block.input if hasattr(block, 'input') else {}
                thinking_to_tool.append({
                    "turn": turn_idx + 1,
                    "tool_type": block.type,
                    "tool": block.name,
                    "tool_id": block.id,
                    "tool_input": tool_input,
                    "preceding_thinking_types": current_thinking.copy(),
                    "preceding_thinking_preview": current_thinking_content.copy(),
                })
                current_thinking = []
                current_thinking_content = []

    print(f"\n  Total tool calls across all turns: {len(thinking_to_tool)}")
    for i, item in enumerate(thinking_to_tool):
        print(f"\n  [{i+1}] Turn {item['turn']} - {item['tool_type']}: '{item['tool']}'")
        print(f"      ID: {item['tool_id']}")
        print(f"      Input: {json.dumps(item['tool_input'])[:100]}")
        print(f"      Preceded by: {item['preceding_thinking_types'] if item['preceding_thinking_types'] else '[no thinking]'}")
        if item['preceding_thinking_preview']:
            for j, preview in enumerate(item['preceding_thinking_preview']):
                print(f"        thinking[{j}]: {preview[:80]}...")

    return all_responses


async def main():
    print("Smoke Tests: Anthropic Extended Thinking Structure")
    print("=" * 60)
    print()

    # await test_anthropic_thinking_text_only()
    # await test_anthropic_thinking_with_tools()
    await test_anthropic_interleaved_thinking()

    print("\n" + "=" * 60)
    print("SMOKE TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
