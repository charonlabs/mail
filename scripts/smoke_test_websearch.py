# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Ryan Heaton

"""
Smoke test for web_search support in LiteLLMAgentFunction

Tests the new native Anthropic SDK path for web_search built-in tools.
"""

import asyncio
import json

from mail.factories.base import LiteLLMAgentFunction


async def test_litellm_agent_function_websearch():
    """Test LiteLLMAgentFunction with web_search tool (non-streaming)"""
    print("=" * 60)
    print("TESTING LiteLLMAgentFunction with web_search (non-streaming)")
    print("=" * 60)

    # Web search tool in Anthropic format
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
        use_proxy=False,  # Bypass LiteLLM proxy, use ANTHROPIC_API_KEY
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
                if citations:
                    print(f"  first citation: {citations[0]}")

        print("\n✅ Test passed!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_litellm_agent_function_websearch_streaming():
    """Test LiteLLMAgentFunction with web_search tool (streaming)"""
    print("\n" + "=" * 60)
    print("TESTING LiteLLMAgentFunction with web_search (streaming)")
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
        stream_tokens=True,  # Enable streaming
        _debug_include_mail_tools=False,
    )

    messages = [
        {"role": "user", "content": "What is the current weather in San Francisco? Search the web for it."}
    ]

    try:
        content, tool_calls = await agent(messages, tool_choice="auto")

        print("\n\n--- CONTENT ---")
        print(content[:500] + "..." if len(content) > 500 else content)

        print("\n--- TOOL CALLS ---")
        for i, tc in enumerate(tool_calls):
            print(f"\nTool Call {i}:")
            print(f"  tool_name: {tc.tool_name}")
            print(f"  tool_call_id: {tc.tool_call_id}")
            if tc.tool_name == "web_search_call":
                print(f"  query: {tc.tool_args.get('query', 'N/A')}")
                results = tc.tool_args.get("results", [])
                print(f"  results count: {len(results)}")
                citations = tc.tool_args.get("citations", [])
                print(f"  citations count: {len(citations)}")

        print("\n✅ Test passed!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_litellm_agent_function_websearch_with_reasoning():
    """Test LiteLLMAgentFunction with web_search tool AND extended thinking"""
    print("\n" + "=" * 60)
    print("TESTING LiteLLMAgentFunction with web_search + reasoning")
    print("=" * 60)

    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }
    ]

    # Use claude-sonnet-4 which supports extended thinking
    agent = LiteLLMAgentFunction(
        name="test_agent",
        comm_targets=[],
        tools=tools,
        llm="anthropic/claude-sonnet-4-20250514",  # Sonnet supports thinking
        system="You are a helpful assistant. Think carefully before answering.",
        tool_format="completions",
        use_proxy=False,
        stream_tokens=True,  # Stream to see reasoning
        reasoning_effort="low",  # Enable extended thinking
        _debug_include_mail_tools=False,
    )

    messages = [
        {"role": "user", "content": "What is the current weather in San Francisco? Search the web and give me a brief summary."}
    ]

    try:
        content, tool_calls = await agent(messages, tool_choice="auto")

        print("\n\n--- CONTENT ---")
        print(content[:500] + "..." if len(content) > 500 else content)

        print("\n--- TOOL CALLS ---")
        for i, tc in enumerate(tool_calls):
            print(f"\nTool Call {i}:")
            print(f"  tool_name: {tc.tool_name}")
            print(f"  tool_args keys: {list(tc.tool_args.keys())}")
            if tc.tool_name == "web_search_call":
                print(f"  query: {tc.tool_args.get('query', 'N/A')}")
                results = tc.tool_args.get("results", [])
                print(f"  results count: {len(results)}")
                citations = tc.tool_args.get("citations", [])
                print(f"  citations count: {len(citations)}")
                reasoning = tc.tool_args.get("reasoning", "")
                if reasoning:
                    print(f"  reasoning length: {len(reasoning)} chars")
                    print(f"  reasoning preview: {reasoning[:200]}...")
                else:
                    print("  reasoning: NOT CAPTURED")

        print("\n✅ Test passed!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_completions_native_anthropic():
    """Test directly with anthropic SDK to see native response format"""
    print("\n" + "=" * 60)
    print("TESTING NATIVE ANTHROPIC SDK (for reference)")
    print("=" * 60)

    try:
        import anthropic
        client = anthropic.Anthropic()

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[
                {"role": "user", "content": "What is the current weather in San Francisco? Search the web for it."}
            ],
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3
            }]
        )

        print("\n--- RESPONSE SUMMARY ---")
        print(f"ID: {response.id}")
        print(f"Model: {response.model}")
        print(f"Stop reason: {response.stop_reason}")
        print(f"Usage: {response.usage}")
        print(f"Content blocks count: {len(response.content)}")

        print("\n--- CONTENT BLOCK TYPES ---")
        for i, block in enumerate(response.content):
            block_dict = block.model_dump()
            block_type = block_dict.get('type', 'unknown')
            print(f"\nBlock {i}: type={block_type}")

            if block_type == 'server_tool_use':
                print(f"  name: {block_dict.get('name')}")
                print(f"  id: {block_dict.get('id')}")
                print(f"  input: {block_dict.get('input')}")
            elif block_type == 'web_search_tool_result':
                print(f"  tool_use_id: {block_dict.get('tool_use_id')}")
                content = block_dict.get('content', [])
                print(f"  results count: {len(content)}")
                if content:
                    print(f"  first result: url={content[0].get('url')}, title={content[0].get('title')}")
            elif block_type == 'text':
                text = block_dict.get('text', '')
                citations = block_dict.get('citations')
                print(f"  text length: {len(text)}")
                print(f"  has citations: {citations is not None}")
                if citations:
                    print(f"  citations count: {len(citations)}")

        print("\n--- FULL RESPONSE (truncated) ---")
        full_dump = response.model_dump()
        # Truncate encrypted content to reduce output
        for block in full_dump.get('content', []):
            if isinstance(block, dict):
                if block.get('type') == 'web_search_tool_result':
                    for result in block.get('content', []):
                        if 'encrypted_content' in result:
                            result['encrypted_content'] = result['encrypted_content'][:50] + '...'
        print(json.dumps(full_dump, indent=2, default=str)[:5000])
        if len(json.dumps(full_dump)) > 5000:
            print("\n... [truncated]")

    except ImportError:
        print("anthropic SDK not installed, skipping native test")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("Smoke Test: web_search support in LiteLLMAgentFunction")
    print()

    # Test the new LiteLLMAgentFunction implementation
    await test_litellm_agent_function_websearch()
    await test_litellm_agent_function_websearch_streaming()
    await test_litellm_agent_function_websearch_with_reasoning()

    print("\n" + "=" * 60)
    print("ALL TESTS DONE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
