# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Ryan Heaton

"""
Smoke test for web_search support in LiteLLMAgentFunction

Tests the new native Anthropic SDK path for web_search built-in tools.
Includes tests for:
- Tool format conversion (MAIL tools + web_search)
- Extended thinking with interleaved thinking
- Thinking blocks with signature capture
- tool_choice compatibility with thinking
"""

import asyncio
import json

from mail.factories.base import LiteLLMAgentFunction


async def test_websearch_basic():
    """Test LiteLLMAgentFunction with web_search tool (non-streaming)"""
    print("=" * 60)
    print("TEST 1: web_search basic (non-streaming)")
    print("=" * 60)

    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }
    ]

    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=[],
        tools=tools,
        llm="anthropic/claude-haiku-4-5-20251001",
        system="You are a helpful assistant.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=False,
        _debug_include_mail_tools=False,
    )

    messages = [
        {"role": "user", "content": "What is the current weather in San Francisco? Search the web for it."}
    ]

    try:
        content, tool_calls = await agent(messages, tool_choice="auto")

        print("\n--- CONTENT ---")
        print(content[:500] + "..." if len(content) > 500 else content)

        print("\n--- TOOL CALLS ---")
        for i, tc in enumerate(tool_calls):
            print(f"\nTool Call {i}:")
            print(f"  tool_name: {tc.tool_name}")
            print(f"  tool_call_id: {tc.tool_call_id}")
            print(f"  tool_args keys: {list(tc.tool_args.keys())}")
            if tc.tool_name == "web_search_call":
                print(f"  query: {tc.tool_args.get('query', 'N/A')}")
                print(f"  status: {tc.tool_args.get('status', 'N/A')}")
                results = tc.tool_args.get("results", [])
                print(f"  results count: {len(results)}")
                if results:
                    print(f"  first result: {results[0]}")
                citations = tc.tool_args.get("citations", [])
                print(f"  citations count: {len(citations)}")

        print("\n✅ Test passed!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_websearch_with_mail_tools():
    """Test web_search alongside MAIL tools (tool format conversion)"""
    print("\n" + "=" * 60)
    print("TEST 2: web_search + MAIL tools (tool format conversion)")
    print("=" * 60)

    # Web search tool in Anthropic format
    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }
    ]

    # Enable MAIL tools by setting comm_targets
    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=["supervisor", "researcher"],  # This will add MAIL tools
        tools=tools,
        llm="anthropic/claude-haiku-4-5-20251001",
        system="You are a helpful assistant in a multi-agent system.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=False,
        _debug_include_mail_tools=True,  # Include MAIL tools
    )

    messages = [
        {"role": "user", "content": "Search the web for current AI news."}
    ]

    try:
        content, tool_calls = await agent(messages, tool_choice="auto")

        print("\n--- CONTENT ---")
        print(content[:300] + "..." if len(content) > 300 else content)

        print("\n--- TOOL CALLS ---")
        for i, tc in enumerate(tool_calls):
            print(f"\nTool Call {i}:")
            print(f"  tool_name: {tc.tool_name}")
            print(f"  tool_args keys: {list(tc.tool_args.keys())}")

        print("\n✅ Test passed! (MAIL tools + web_search coexist)")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_websearch_streaming():
    """Test web_search with streaming"""
    print("\n" + "=" * 60)
    print("TEST 3: web_search streaming")
    print("=" * 60)

    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }
    ]

    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=[],
        tools=tools,
        llm="anthropic/claude-haiku-4-5-20251001",
        system="You are a helpful assistant.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=True,
        _debug_include_mail_tools=False,
    )

    messages = [
        {"role": "user", "content": "What is the current weather in San Francisco? Search the web."}
    ]

    try:
        content, tool_calls = await agent(messages, tool_choice="auto")

        print("\n\n--- CONTENT ---")
        print(content[:300] + "..." if len(content) > 300 else content)

        print("\n--- TOOL CALLS ---")
        for i, tc in enumerate(tool_calls):
            print(f"\nTool Call {i}:")
            print(f"  tool_name: {tc.tool_name}")
            if tc.tool_name == "web_search_call":
                print(f"  query: {tc.tool_args.get('query', 'N/A')}")
                results = tc.tool_args.get("results", [])
                print(f"  results count: {len(results)}")

        print("\n✅ Test passed!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_extended_thinking_with_interleaved():
    """Test extended thinking with interleaved thinking beta"""
    print("\n" + "=" * 60)
    print("TEST 4: Extended thinking + interleaved thinking")
    print("=" * 60)

    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }
    ]

    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=[],
        tools=tools,
        llm="anthropic/claude-sonnet-4-20250514",
        system="You are a helpful assistant. Think step by step.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=True,
        reasoning_effort="low",  # Enable extended thinking
        _debug_include_mail_tools=False,
    )

    messages = [
        {"role": "user", "content": "Search for the latest news about AI safety and summarize it briefly."}
    ]

    try:
        content, tool_calls = await agent(messages, tool_choice="auto")

        print("\n\n--- CONTENT ---")
        print(content[:400] + "..." if len(content) > 400 else content)

        print("\n--- TOOL CALLS ---")
        for i, tc in enumerate(tool_calls):
            print(f"\nTool Call {i}:")
            print(f"  tool_name: {tc.tool_name}")
            print(f"  tool_args keys: {list(tc.tool_args.keys())}")

            # Check for thinking blocks
            thinking_blocks = tc.tool_args.get("thinking_blocks", [])
            if thinking_blocks:
                print(f"  thinking_blocks count: {len(thinking_blocks)}")
                for j, tb in enumerate(thinking_blocks):
                    tb_type = tb.get("type", "unknown")
                    print(f"    block {j}: type={tb_type}")
                    if tb_type == "thinking":
                        has_signature = bool(tb.get("signature"))
                        thinking_preview = tb.get("thinking", "")[:100]
                        print(f"      has_signature: {has_signature}")
                        print(f"      thinking preview: {thinking_preview}...")
                    elif tb_type == "redacted_thinking":
                        print(f"      data length: {len(tb.get('data', ''))}")
            else:
                print("  thinking_blocks: NONE")

            # Check for reasoning text
            reasoning = tc.tool_args.get("reasoning", "")
            if reasoning:
                print(f"  reasoning length: {len(reasoning)} chars")
                print(f"  reasoning preview: {reasoning[:150]}...")
            else:
                print("  reasoning: NONE")

        print("\n✅ Test passed!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_tool_choice_required_with_thinking():
    """Test that tool_choice='required' falls back to 'auto' with thinking enabled"""
    print("\n" + "=" * 60)
    print("TEST 5: tool_choice='required' with thinking (should fallback to auto)")
    print("=" * 60)

    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }
    ]

    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=[],
        tools=tools,
        llm="anthropic/claude-haiku-4-5-20251001",
        system="You are a helpful assistant.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=False,
        reasoning_effort="low",  # Enable thinking
        _debug_include_mail_tools=False,
    )

    messages = [
        {"role": "user", "content": "Search for today's date."}
    ]

    try:
        # This should NOT error - should fall back to "auto"
        content, tool_calls = await agent(messages, tool_choice="required")

        print("\n--- CONTENT ---")
        print(content[:300] + "..." if len(content) > 300 else content)

        print("\n--- TOOL CALLS ---")
        for i, tc in enumerate(tool_calls):
            print(f"\nTool Call {i}:")
            print(f"  tool_name: {tc.tool_name}")

            # Check thinking blocks are captured
            thinking_blocks = tc.tool_args.get("thinking_blocks", [])
            print(f"  thinking_blocks count: {len(thinking_blocks)}")

        print("\n✅ Test passed! (tool_choice fallback worked)")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_thinking_blocks_structure():
    """Test that thinking blocks have correct structure (type, thinking, signature)"""
    print("\n" + "=" * 60)
    print("TEST 6: Thinking blocks structure validation")
    print("=" * 60)

    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 2,
        }
    ]

    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=[],
        tools=tools,
        llm="anthropic/claude-haiku-4-5-20251001",
        system="You are a helpful assistant.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=False,
        reasoning_effort="low",
        _debug_include_mail_tools=False,
    )

    messages = [
        {"role": "user", "content": "What day is it today? Search if needed."}
    ]

    try:
        content, tool_calls = await agent(messages, tool_choice="auto")

        print("\n--- Validating thinking block structure ---")

        all_valid = True
        for tc in tool_calls:
            thinking_blocks = tc.tool_args.get("thinking_blocks", [])

            for i, tb in enumerate(thinking_blocks):
                print(f"\nBlock {i}:")

                # Check type field
                block_type = tb.get("type")
                print(f"  type: {block_type}")
                if block_type not in ("thinking", "redacted_thinking"):
                    print(f"  ❌ Invalid type!")
                    all_valid = False

                if block_type == "thinking":
                    # Check thinking field
                    thinking = tb.get("thinking")
                    if thinking:
                        print(f"  thinking: {len(thinking)} chars")
                    else:
                        print(f"  ❌ Missing thinking field!")
                        all_valid = False

                    # Check signature field
                    signature = tb.get("signature")
                    if signature:
                        print(f"  signature: {len(signature)} chars (present)")
                    else:
                        print(f"  ⚠️ Missing signature (may be ok for some models)")

                elif block_type == "redacted_thinking":
                    # Check data field
                    data = tb.get("data")
                    if data:
                        print(f"  data: {len(data)} chars (encrypted)")
                    else:
                        print(f"  ❌ Missing data field!")
                        all_valid = False

        if all_valid:
            print("\n✅ All thinking blocks have valid structure!")
        else:
            print("\n⚠️ Some blocks had issues")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("=" * 60)
    print("Smoke Tests: Native Anthropic SDK with web_search")
    print("=" * 60)
    print()

    await test_websearch_basic()
    await test_websearch_with_mail_tools()
    await test_websearch_streaming()
    await test_extended_thinking_with_interleaved()
    await test_tool_choice_required_with_thinking()
    await test_thinking_blocks_structure()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
