# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Ryan Heaton

"""
Smoke test to investigate OAI Responses API reasoning structure.

Tests both streaming and non-streaming paths to understand where reasoning
summary lives on the response objects.
"""

import asyncio
import os

from litellm.llms.openai.responses.transformation import ResponsesAPIResponse
from litellm.responses.main import aresponses
import litellm
import rich


async def test_oai_reasoning_non_streaming():
    """Test non-streaming OAI Responses API to see reasoning structure."""
    print("=" * 60)
    print("TEST: OAI Responses API - Non-Streaming")
    print("=" * 60)

    litellm.drop_params = True

    messages = [
        {
            "role": "user",
            "content": """Solve this logic puzzle step by step:
Five houses in a row are painted different colors. In each house lives a person of a different nationality.
Each person drinks a different beverage, smokes a different brand of cigar, and keeps a different pet.
Clues:
1. The Brit lives in the red house.
2. The Swede keeps dogs.
3. The Dane drinks tea.
4. The green house is just to the left of the white house.
5. The owner of the green house drinks coffee.
6. The person who smokes Pall Mall keeps birds.
7. The owner of the yellow house smokes Dunhill.
8. The person in the middle house drinks milk.
9. The Norwegian lives in the first house.
10. The Chesterfield smoker lives next to the fox owner.
11. The Dunhill smoker lives next to the horse owner.
12. The Winfield smoker drinks beer.
13. The German smokes Rothmanns.
14. The Norwegian lives next to the blue house.
15. The Chesterfield smoker has a neighbor who drinks water.
Who owns the fish?""",
        }
    ]

    tools = [
        {
            "type": "function",
            "name": "answer",
            "description": "Provide the answer",
            "parameters": {
                "type": "object",
                "properties": {
                    "result": {"type": "string", "description": "The answer"},
                },
                "required": ["result"],
            },
        }
    ]

    res = await aresponses(
        input=messages,
        model="openai/gpt-5.2",
        max_output_tokens=8192,
        include=["reasoning.encrypted_content"],
        reasoning={"effort": "high", "summary": "detailed"},
        tool_choice="required",
        tools=tools,
    )

    print("\n--- Response Type ---")
    print(f"Type: {type(res)}")

    print("\n--- Response Attributes ---")
    for attr in dir(res):
        if not attr.startswith("_"):
            try:
                val = getattr(res, attr)
                if not callable(val):
                    print(f"  {attr}: {type(val).__name__} = {repr(val)[:200]}")
            except Exception as e:
                print(f"  {attr}: ERROR - {e}")

    print("\n--- model_dump() ---")
    try:
        dump = res.model_dump()
        for key, val in dump.items():
            print(f"  {key}: {type(val).__name__} = {repr(val)[:300]}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n--- Output Items ---")
    for i, output in enumerate(res.output):
        print(f"\n  Output {i}:")
        if isinstance(output, dict):
            for k, v in output.items():
                print(f"    {k}: {repr(v)[:200]}")
        else:
            for attr in dir(output):
                if not attr.startswith("_"):
                    try:
                        val = getattr(output, attr)
                        if not callable(val):
                            print(f"    {attr}: {repr(val)[:200]}")
                    except:
                        pass


async def test_oai_reasoning_streaming():
    """Test streaming OAI Responses API to see reasoning events and final response."""
    print("\n" + "=" * 60)
    print("TEST: OAI Responses API - Streaming")
    print("=" * 60)

    litellm.drop_params = True

    messages = [
        {
            "role": "user",
            "content": """Solve this logic puzzle step by step:
Five houses in a row are painted different colors. In each house lives a person of a different nationality.
Each person drinks a different beverage, smokes a different brand of cigar, and keeps a different pet.
Clues:
1. The Brit lives in the red house.
2. The Swede keeps dogs.
3. The Dane drinks tea.
4. The green house is just to the left of the white house.
5. The owner of the green house drinks coffee.
6. The person who smokes Pall Mall keeps birds.
7. The owner of the yellow house smokes Dunhill.
8. The person in the middle house drinks milk.
9. The Norwegian lives in the first house.
10. The Chesterfield smoker lives next to the fox owner.
11. The Dunhill smoker lives next to the horse owner.
12. The Winfield smoker drinks beer.
13. The German smokes Rothmanns.
14. The Norwegian lives next to the blue house.
15. The Chesterfield smoker has a neighbor who drinks water.
Who owns the fish?""",
        }
    ]

    tools = [
        {
            "type": "function",
            "name": "answer",
            "description": "Provide the answer",
            "parameters": {
                "type": "object",
                "properties": {
                    "result": {"type": "string", "description": "The answer"},
                },
                "required": ["result"],
            },
        }
    ]

    stream = await aresponses(
        input=messages,
        model="openai/gpt-5.2",
        max_output_tokens=8192,
        include=["reasoning.encrypted_content"],
        reasoning={"effort": "high", "summary": "detailed"},
        tool_choice="required",
        tools=tools,
        stream=True,
    )

    reasoning_events = []
    final_response = None
    all_event_types = set()

    print("\n--- Streaming Events ---")
    async for event in stream:
        all_event_types.add(event.type)

        if "reasoning" in event.type.lower():
            reasoning_events.append(event)
            print(f"  REASONING EVENT: {event.type}")
            if hasattr(event, "delta"):
                print(f"    delta: {repr(event.delta)[:100]}")

        if event.type == "response.completed":
            final_response = event.response
            print(f"  COMPLETED: Got final response")

    print(f"\n--- All Event Types Seen ---")
    for et in sorted(all_event_types):
        print(f"  {et}")

    print(f"\n--- Reasoning Events ({len(reasoning_events)}) ---")
    for i, evt in enumerate(reasoning_events):
        print(f"  Event {i}: type={evt.type}")
        for attr in dir(evt):
            if not attr.startswith("_"):
                try:
                    val = getattr(evt, attr)
                    if not callable(val):
                        print(f"    {attr}: {repr(val)[:200]}")
                except:
                    pass

    if final_response:
        print("\n--- Final Response Attributes ---")
        for attr in dir(final_response):
            if not attr.startswith("_"):
                try:
                    val = getattr(final_response, attr)
                    if not callable(val):
                        print(f"  {attr}: {type(val).__name__} = {repr(val)[:200]}")
                except Exception as e:
                    print(f"  {attr}: ERROR - {e}")

        print("\n--- Final Response model_dump() ---")
        try:
            dump = final_response.model_dump()
            for key, val in dump.items():
                print(f"  {key}: {type(val).__name__} = {repr(val)[:300]}")
        except Exception as e:
            print(f"  ERROR: {e}")


async def main():
    print("Smoke Tests: OAI Responses API Reasoning Structure")
    print("=" * 60)
    print()

    await test_oai_reasoning_non_streaming()
    await test_oai_reasoning_streaming()

    print("\n" + "=" * 60)
    print("SMOKE TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
