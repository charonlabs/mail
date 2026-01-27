# Reasoning Trace Smoke Test Findings

## Overview

This document captures findings from smoke tests investigating where reasoning/thinking content lives in different LLM API responses, to inform implementation of reasoning traces in tool call events.

---

## OpenAI Responses API (gpt-5.2)

**Test Date:** 2026-01-06
**Model:** `openai/gpt-5.2` (resolved to `gpt-5.2-2025-12-11`)
**Test Question:** Einstein's Zebra Puzzle (complex logic puzzle requiring significant reasoning)

### Configuration

```python
await aresponses(
    input=messages,
    model="openai/gpt-5.2",
    max_output_tokens=8192,
    include=["reasoning.encrypted_content"],
    reasoning={"effort": "high", "summary": "detailed"},
    tool_choice="required",
    tools=tools,
    stream=True/False,
)
```

### Non-Streaming Response

**Result:** ✅ Reasoning summary IS available

**Location:** `response.output` array contains a `ResponseReasoningItem` with:
- `type: "reasoning"`
- `summary: List[Summary]` - Array of summary objects
- `encrypted_content: str` - Encrypted raw reasoning (not usable)

**Extraction Path:**
```python
for output in res.output:
    if output.type == "reasoning":
        for summary_item in output.summary:
            reasoning_text = summary_item.text  # <-- This is the reasoning summary
```

**Example Output Structure:**
```python
ResponseReasoningItem(
    id='rs_0f0806c96bd0a13f00695dbf738bc081928f41c6fa089b9f24',
    type='reasoning',
    summary=[
        Summary(text="**Analyzing Chesterfield location**\n\nI'm figuring out the possible locations...")
    ],
    content=None,
    encrypted_content='gAAAAABpXb-iTrxe8Argm1GqrIMN83Zy...'
)
```

**Usage Stats:**
- `reasoning_tokens: 1726` (in `usage.output_tokens_details`)

**Important Notes:**
- The `summary` field can be EMPTY (`[]`) if the model didn't need to reason much
- Simple questions may not generate any summary content
- The `reasoning` field on the response object is just the CONFIG (`{'effort': 'high', 'summary': 'detailed'}`), NOT the actual reasoning

### Streaming Response

**Result:** ✅ Reasoning summary IS available via streaming events

**Event Types:**
```
response.reasoning_summary_part.added    - Start of a summary part
response.reasoning_summary_text.delta    - Text chunk of reasoning summary
response.reasoning_summary_text.done     - End of text for this part
response.reasoning_summary_part.done     - End of summary part
```

**Extraction Approach:**
```python
reasoning_parts = []

async for event in stream:
    if event.type == "response.reasoning_summary_text.delta":
        reasoning_parts.append(event.delta)
    elif event.type == "response.completed":
        final_response = event.response

reasoning_summary = "".join(reasoning_parts)
```

**Event Structure (delta events):**
```python
{
    'type': 'response.reasoning_summary_text.delta',
    'sequence_number': 4,
    'item_id': 'rs_022a860c041198e700695dbea537c48190a36863cbcb1aaec5',
    'output_index': 0,
    'summary_index': 0,
    'delta': '**Analy',  # <-- Text chunk
    'obfuscation': 'XTdhgYI7d'
}
```

**Important Notes:**
- The final `response.completed` event's `response.output` does NOT include the reasoning item
- You MUST capture reasoning from streaming events, cannot get it from final response
- 107 reasoning events captured for the zebra puzzle test
- Events come with `obfuscation` field (purpose unclear, possibly for watermarking)

### Key Differences: Streaming vs Non-Streaming

| Aspect | Non-Streaming | Streaming |
|--------|--------------|-----------|
| Reasoning in final response | Yes, in `output` array | No |
| How to capture | `output[i].summary[j].text` | Accumulate `delta` events |
| Event types needed | N/A | `response.reasoning_summary_text.delta` |

### Interleaved Reasoning (CONFIRMED)

**Test Date:** 2026-01-06
**Model:** `openai/gpt-5.2`
**Test:** Multi-tool conversation with web_search and analyze_tradeoffs

**Result:** ✅ OAI DOES have interleaved reasoning!

**Observed Output Sequence:**
```
reasoning -> web_search_call -> reasoning -> function_call
```

**Analysis:**
- Reasoning items at indices: [0, 2]
- Tool items at indices: [1, 3]
- **MULTIPLE REASONING BLOCKS DETECTED**
- **REASONING AFTER TOOL CALL at index [2]**

**Implication:** Must use `pending_reasoning` pattern (same as Anthropic) - each tool gets the reasoning that preceded it, not just "first tool gets all reasoning".

---

## Anthropic Native API (Claude)

**Test Date:** 2026-01-06
**Model:** `claude-sonnet-4-5-20250929`
**Test:** Multi-turn conversation with web_search (server_tool_use), analyze_tradeoffs, and report_findings tools

### Configuration

```python
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
        "anthropic-beta": "interleaved-thinking-2025-05-14"  # REQUIRED for interleaved thinking!
    },
)
```

### Content Block Types Observed

- `thinking` - Contains reasoning with `thinking` and `signature` fields
- `text` - Text output (model's verbal response)
- `server_tool_use` - Server-side tools (web_search)
- `web_search_tool_result` - Result from web_search (comes in SAME response!)
- `tool_use` - Client-side tool calls

### Actual Interleaving Pattern (WITH beta header)

**With `interleaved-thinking-2025-05-14` beta header, TRUE interleaving occurs!**

**Turn 1 Block Sequence:**
```
thinking -> text -> server_tool_use -> web_search_tool_result -> thinking -> text... -> tool_use
```

Note: **TWO thinking blocks** in Turn 1 - one before web_search, one AFTER receiving results before analyze_tradeoffs!

**Turn 2 Block Sequence:**
```
thinking -> text -> tool_use
```

**Turn 3 Block Sequence (final):**
```
thinking -> text
```

### Key Findings

1. **With interleaved-thinking beta, each tool call can have its own preceding thinking**
2. **Thinking appears AFTER receiving tool results** (e.g., after web_search_tool_result)
3. **server_tool_use and web_search_tool_result come together** in the same response
4. **text blocks appear between tool operations** (model explaining what it's doing)
5. **Even final text responses have preceding thinking** (Turn 3)

### Interleaving Analysis Results

| Tool Call | Turn | Type | Preceded By |
|-----------|------|------|-------------|
| web_search | 1 | server_tool_use | `['thinking']` |
| analyze_tradeoffs | 1 | tool_use | `['thinking']` ← SECOND thinking block! |
| report_findings | 2 | tool_use | `['thinking']` |

### Implementation Implications

**With interleaved-thinking beta header enabled:**

**Actual pattern within a turn:**
```
thinking -> [text] -> tool1 -> [result1] -> thinking -> [text] -> tool2 -> ...
```

**For reasoning attribution:**
1. **Each tool call gets its own preceding thinking** (if the model generated one)
2. **Thinking can appear AFTER tool results** - model reasons about what it learned
3. **Parallel tool calls** (if any) would share the preceding thinking block
4. **Use `reasoning_ref` only for truly parallel calls** with no thinking between them

### Thinking Block Structure

```python
{
    "type": "thinking",
    "thinking": "The user wants me to research Python 3.13...",
    "signature": "ErUBCkYIARAB..."  # Cryptographic signature
}
```

### Server Tool Result Structure

The `web_search_tool_result` block appears in the SAME response as `server_tool_use`:
- No separate API call needed for server tool results
- Must be included when reconstructing assistant messages for multi-turn

### Extraction Approach

```python
# Within a single response/turn - with interleaved thinking, each tool gets its own thinking
pending_thinking = []
pending_thinking_content = []

for block in response.content:
    if block.type == "thinking":
        pending_thinking.append(block.type)
        pending_thinking_content.append(block.thinking)
    elif block.type == "redacted_thinking":
        pending_thinking.append(block.type)
        pending_thinking_content.append("[REDACTED]")
    elif block.type in ("tool_use", "server_tool_use"):
        tool_call = AgentToolCall(
            tool_name=block.name,
            tool_args=block.input,
            tool_call_id=block.id,
        )
        if pending_thinking:
            # This tool gets all accumulated thinking since last tool
            tool_call.tool_args["thinking_blocks"] = [
                {"type": t, "content": c}
                for t, c in zip(pending_thinking, pending_thinking_content)
            ]
            pending_thinking = []  # Reset for next tool
            pending_thinking_content = []
        tool_calls.append(tool_call)
    # Skip text, web_search_tool_result - not tool calls

# For text_output (text-only responses), attach any remaining thinking
if not tool_calls and pending_thinking:
    # Create text_output with accumulated thinking
    tool_call.tool_args["thinking_blocks"] = [...]
```

### Edge Cases

1. **No thinking before a tool** - Some tools may have no preceding thinking (use `reasoning_ref`)
2. **Multiple thinking blocks before one tool** - Join with newlines, all go to that tool
3. **redacted_thinking** - Handle with `[REDACTED]` placeholder
4. **text blocks between tools** - Ignore for reasoning attribution (they're explanatory text)
5. **web_search_tool_result** - Not a tool call; include in message history but don't emit event
6. **Parallel tool calls** - If multiple tool_use blocks appear consecutively without thinking between, first gets reasoning, others get `reasoning_ref`
7. **Final text with thinking** - Turn 3 showed `thinking -> text` pattern; if no tool_use, thinking goes to text_output

---

## Implementation Recommendations

### For OpenAI Responses API

**Non-Streaming (`_run_responses`):**
```python
# After getting response
reasoning_summary = None
for output in res.output:
    if hasattr(output, 'type') and output.type == 'reasoning':
        if hasattr(output, 'summary') and output.summary:
            # Join all summary texts
            reasoning_summary = "\n".join(
                s.text for s in output.summary if hasattr(s, 'text')
            )
        break

# Attach to first tool call
if reasoning_summary and tool_calls:
    tool_calls[0].tool_args["reasoning"] = reasoning_summary
```

**Streaming (`_stream_responses`):**
```python
reasoning_parts = []

async for event in stream:
    match event.type:
        case "response.reasoning_summary_text.delta":
            reasoning_parts.append(event.delta)
            # Optionally print for visibility
            print(event.delta, end="", flush=True)
        case "response.completed":
            final_response = event.response

# After streaming, attach to first tool call
reasoning_summary = "".join(reasoning_parts)
if reasoning_summary and tool_calls:
    tool_calls[0].tool_args["reasoning"] = reasoning_summary
```

### For Anthropic API

```python
# Track pending thinking blocks
pending_thinking = []

for block in response.content:
    if block.type == "thinking":
        pending_thinking.append(block.thinking)
    elif block.type == "redacted_thinking":
        pending_thinking.append("[redacted thinking]")
    elif block.type in ("tool_use", "server_tool_use"):
        # Create tool call with accumulated thinking
        tool_call = AgentToolCall(...)
        if pending_thinking:
            tool_call.tool_args["thinking_blocks"] = pending_thinking.copy()
            pending_thinking = []  # Reset for next tool
        tool_calls.append(tool_call)
    elif block.type == "text":
        # For text-only, thinking goes to text_output
        text_thinking = pending_thinking.copy()
        pending_thinking = []
```

---

## Test Script

Location: `scripts/smoke_test_reasoning.py`

Runs both streaming and non-streaming tests against OpenAI gpt-5.2 with Einstein's Zebra Puzzle to ensure sufficient reasoning is generated.
