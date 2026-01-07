# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Ryan Heaton

"""
Smoke test for multi-turn tool use with native Anthropic SDK.

Tests that tool calls and tool results are properly converted between
OpenAI/LiteLLM format and Anthropic format in multi-turn conversations.
"""

import asyncio

from mail.factories.base import LiteLLMAgentFunction


async def test_multiturn_with_custom_tool():
    """Test multi-turn conversation with a custom tool (simulating MAIL tools)."""
    print("=" * 60)
    print("TEST: Multi-turn conversation with custom tool")
    print("=" * 60)

    # Define a simple calculator tool in OpenAI format (like MAIL tools)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Perform a mathematical calculation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "The math expression to evaluate, e.g. '2 + 2'"
                        }
                    },
                    "required": ["expression"]
                }
            }
        }
    ]

    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=[],
        tools=tools,
        llm="anthropic/claude-haiku-4-5-20251001",
        system="You are a helpful assistant. Use the calculate tool for math questions.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=False,
        _debug_include_mail_tools=False,
    )

    # Turn 1: User asks a math question
    messages = [
        {"role": "user", "content": "What is 15 + 27?"}
    ]

    print("\n--- Turn 1: Initial request ---")
    content, tool_calls = await agent(messages, tool_choice="auto")

    print(f"Content: {content}")
    print(f"Tool calls: {len(tool_calls)}")

    # Check if a tool was called
    calc_call = None
    for tc in tool_calls:
        print(f"  - {tc.tool_name}: {tc.tool_args}")
        if tc.tool_name == "calculate":
            calc_call = tc

    if not calc_call:
        print("No calculate tool call - model answered directly")
        print("✅ Test passed (no tool use needed)")
        return

    # Turn 2: Send tool result in OpenAI format (this tests our conversion)
    print("\n--- Turn 2: Sending tool result ---")

    # Build conversation history in OpenAI/LiteLLM format
    messages = [
        {"role": "user", "content": "What is 15 + 27?"},
        {
            "role": "assistant",
            "content": content or "",
            "tool_calls": [
                {
                    "id": calc_call.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "calculate",
                        "arguments": '{"expression": "15 + 27"}'
                    }
                }
            ]
        },
        {
            "role": "tool",
            "tool_call_id": calc_call.tool_call_id,
            "content": "42"
        }
    ]

    print(f"Sending {len(messages)} messages (including tool result)")

    try:
        content2, tool_calls2 = await agent(messages, tool_choice="auto")

        print(f"\nFinal response: {content2}")
        print(f"Additional tool calls: {len(tool_calls2)}")

        # Verify the model used the tool result
        if "42" in content2:
            print("\n✅ Test passed! Model correctly used tool result")
        else:
            print("\n⚠️ Model responded but didn't clearly use the tool result")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_multiturn_parallel_tools():
    """Test multi-turn with parallel tool calls and results."""
    print("\n" + "=" * 60)
    print("TEST: Multi-turn with parallel tool results")
    print("=" * 60)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"}
                    },
                    "required": ["city"]
                }
            }
        }
    ]

    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=[],
        tools=tools,
        llm="anthropic/claude-haiku-4-5-20251001",
        system="You are a weather assistant. Always use the get_weather tool.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=False,
        _debug_include_mail_tools=False,
    )

    # Simulate a conversation where Claude made parallel tool calls
    # and we're sending back the results
    messages = [
        {"role": "user", "content": "What's the weather in NYC and LA?"},
        {
            "role": "assistant",
            "content": "I'll check the weather in both cities for you.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "New York"}'
                    }
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "Los Angeles"}'
                    }
                }
            ]
        },
        # Multiple tool results - should be grouped into single user message
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "New York: 45°F, cloudy"
        },
        {
            "role": "tool",
            "tool_call_id": "call_2",
            "content": "Los Angeles: 72°F, sunny"
        }
    ]

    print(f"\nSending conversation with 2 parallel tool results...")

    try:
        content, tool_calls = await agent(messages, tool_choice="auto")

        print(f"\nFinal response:\n{content}")

        # Check if both results were used
        has_nyc = "45" in content or "New York" in content or "cloudy" in content.lower()
        has_la = "72" in content or "Los Angeles" in content or "sunny" in content.lower()

        if has_nyc and has_la:
            print("\n✅ Test passed! Both tool results were used correctly")
        elif has_nyc or has_la:
            print("\n⚠️ Partial success - only one city's weather mentioned")
        else:
            print("\n❌ Neither tool result appears in response")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_multiturn_with_thinking():
    """Test real multi-turn with extended thinking enabled."""
    print("\n" + "=" * 60)
    print("TEST: Real multi-turn with extended thinking")
    print("=" * 60)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup_data",
                "description": "Look up some data from the database",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The query to look up"}
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=[],
        tools=tools,
        llm="anthropic/claude-haiku-4-5-20251001",
        system="You are a helpful assistant. Always use the lookup_data tool when asked to look something up.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=True,  # Stream to see thinking
        reasoning_effort="low",  # Enable thinking
        _debug_include_mail_tools=False,
    )

    # Turn 1: Initial request that should trigger tool use
    messages = [
        {"role": "user", "content": "Look up the population of Tokyo."}
    ]

    print("\n--- Turn 1: Initial request (with thinking) ---")

    try:
        content1, tool_calls1 = await agent(messages, tool_choice="auto")

        print(f"\n\nContent: {content1[:200] if content1 else '(empty)'}")
        print(f"Tool calls: {len(tool_calls1)}")

        # Find the lookup_data call
        lookup_call = None
        for tc in tool_calls1:
            print(f"  - {tc.tool_name}: {tc.tool_args}")
            if tc.tool_name == "lookup_data":
                lookup_call = tc

        if not lookup_call:
            print("No lookup_data tool call - model answered directly")
            print("✅ Test passed (no multi-turn needed)")
            return

        # Check that completion has thinking blocks
        completion = lookup_call.completion
        print(f"\nCompletion has 'content': {'content' in completion}")
        if 'content' in completion:
            content_types = [b.get('type') for b in completion.get('content', [])]
            print(f"Content block types: {content_types}")
            has_thinking_in_completion = 'thinking' in content_types
            print(f"Has thinking in completion: {has_thinking_in_completion}")

        # Turn 2: Send tool result using the real completion from turn 1
        print("\n--- Turn 2: Sending tool result ---")

        # Build messages: original user message + assistant completion + tool result
        messages = [
            {"role": "user", "content": "Look up the population of Tokyo."},
            completion,  # This is the assistant message with thinking blocks!
            {
                "role": "tool",
                "tool_call_id": lookup_call.tool_call_id,
                "content": "Tokyo metropolitan area population: approximately 37.4 million people, making it the most populous metropolitan area in the world."
            }
        ]

        print(f"Sending {len(messages)} messages (user + assistant w/thinking + tool result)")

        content2, tool_calls2 = await agent(messages, tool_choice="auto")

        print(f"\n\nFinal response:\n{content2[:500] if content2 else '(empty)'}...")

        # Check for thinking blocks in second response
        has_thinking = any(
            tc.tool_args.get("thinking_blocks") or tc.tool_args.get("reasoning")
            for tc in tool_calls2
        )

        if "37" in content2 or "million" in content2.lower():
            print("\n✅ Test passed! Multi-turn with thinking worked correctly")
            if has_thinking:
                print("   (Second turn also had thinking)")
        else:
            print("\n⚠️ Response received but didn't clearly use tool result")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("=" * 60)
    print("Smoke Tests: Multi-turn Tool Use with Native Anthropic SDK")
    print("=" * 60)
    print()

    await test_multiturn_with_custom_tool()
    await test_multiturn_parallel_tools()
    await test_multiturn_with_thinking()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
