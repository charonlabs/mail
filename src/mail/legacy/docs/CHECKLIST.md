# Reasoning Trace Implementation Checklist

Use this checklist to implement the reasoning trace plan in order. Do not move to the next step until the "Verify" items are checked.

## Step 0 - Extend AgentToolCall

- [ ] Add `reasoning: list[str] | None` to `AgentToolCall` (keep existing fields and validator).
- [ ] Add `preamble: str | None` to `AgentToolCall` (keep existing fields and validator).
- [ ] Confirm no other fields are removed or defaults changed.

**Verify**
- [ ] `AgentToolCall` still validates `completion` OR `responses` non-empty.
- [ ] New fields are optional and do not affect existing call sites.

---

## Step 1 - Emit tool_call Events

- [ ] Add `_emit_tool_call_event(...)` to `src/mail/core/runtime.py`.
- [ ] Join `call.reasoning` with `"\n\n"` after filtering empty/whitespace-only blocks.
- [ ] Include `preamble` when present.

**Verify**
- [ ] Events include `tool_name`, `tool_args`, `tool_call_id`.
- [ ] `reasoning_ref` is only set when reasoning is absent.

---

## Step 2 - Remove Old tool_args Assignments

- [ ] Remove `tool_args["reasoning"]` and `tool_args["thinking_blocks"]` assignments in `_run_completions_anthropic_native()`.
- [ ] Remove `tool_args["reasoning"]` and `tool_args["thinking_blocks"]` assignments in `_stream_completions_anthropic_native()`.
- [ ] Remove any now-dead `thinking_content` extraction blocks tied only to those assignments.

**Verify**
- [ ] No remaining `tool_args["reasoning"]` or `tool_args["thinking_blocks"]` in `src/mail/factories/base.py`.
- [ ] Anthropic assistant message dict still contains full thinking blocks via `completion`.

---

## Step 3 - Generate UUIDs for text_output

- [ ] Add `uuid.uuid4()` IDs for `text_output` tool calls in:
  - [ ] `_run_completions()` (generic LiteLLM path - UUID only, no reasoning extraction)
  - [ ] `_run_completions_anthropic_native()`
  - [ ] `_stream_completions_anthropic_native()`
  - [ ] `_run_responses()`
- [ ] Keep `tool_args={"content": ...}` unchanged.

**Verify**
- [ ] All `text_output` calls now have non-empty `tool_call_id`.
- [ ] `content` key is preserved (no `text` key introduced).

---

## Step 4 - Emit tool_call Events Before Mutations

- [ ] In `src/mail/core/runtime.py`, emit `tool_call` events at the top of the tool processing loop.
- [ ] Track `last_reasoning_call_id` and use it for `reasoning_ref` when needed.
- [ ] Ensure the event is emitted before any tool-specific mutations (e.g., adding `target`).

**Verify**
- [ ] `reasoning_ref` points to the most recent call with reasoning.
- [ ] Events are emitted for all calls in original order.

---

## Step 5 - Tool Coverage

- [ ] Ensure `tool_call` events are emitted for:
  - [ ] MAIL tools (send_request/send_response/send_interrupt/send_broadcast/task_complete)
  - [ ] Actions
  - [ ] Builtins (web_search_call, code_interpreter_call)
  - [ ] await_message
  - [ ] help
  - [ ] acknowledge/ignore broadcast
  - [ ] breakpoints (emit before existing `breakpoint_tool_call` event)

**Verify**
- [ ] No tool path bypasses `tool_call` emission.
- [ ] Breakpoint tool calls emit `tool_call` before `breakpoint_tool_call`.

---

## Step 6 - OAI Streaming Reasoning (Interleaved)

- [ ] Update `_stream_responses()` to collect reasoning via `response.reasoning_summary_text.delta`.
- [ ] Use `response.output_item.added` to map reasoning to tool outputs (by `output_index`).
- [ ] Flush `current_reasoning_text` on `response.completed`.
- [ ] Return 3-tuple: `(response, tool_reasoning_map, streaming_pending_reasoning)`.
- [ ] Handle dict and object event items.
- [ ] Update `_run_responses()` call site to unpack 3-tuple (was just `response`).

**Verify**
- [ ] Reasoning deltas are joined with `""` (not newlines).
- [ ] `tool_reasoning_map` keys align with `res.output` indices.
- [ ] Streaming fallback reasoning is available for text-only responses.

---

## Step 7 - OAI Single-Pass Collection (Non-Streaming + Streaming Attach)

- [ ] Replace multi-pass tool collection with a single-pass over `res.output`.
- [ ] Handle both dict and object output formats for:
  - [ ] reasoning
  - [ ] message
  - [ ] function_call
  - [ ] web_search_call
  - [ ] code_interpreter_call
- [ ] Attach `responses=outputs` to every `AgentToolCall`.
- [ ] Use `tool_reasoning_map` (when streaming) to fill reasoning if inline extraction is empty.
- [ ] Use `streaming_pending_reasoning` only for text-only fallback (when no tool calls exist).
- [ ] Keep richer builtin fields (status, outputs, search_type).

**Verify**
- [ ] Tool call ordering matches `res.output`.
- [ ] Builtins still hit runtime builtin branches (`web_search_call`, `code_interpreter_call`).
- [ ] Text-only responses create `text_output` with the first message chunk.

---

## Step 8 - Anthropic Interleaved Thinking

- [ ] Rebuild tool call assembly to track `pending_reasoning` and `pending_preamble` by block order.
- [ ] Use `[redacted thinking]` placeholder for `redacted_thinking`.
- [ ] Store reasoning as list[str] on the call, not in `tool_args`.
- [ ] Preserve `completion` for history.

**Verify**
- [ ] Each tool call gets only the reasoning since the previous tool call.
- [ ] Text blocks contribute to preamble; thinking blocks do not reset on text.
- [ ] Text-only responses create `text_output` with `preamble=None`.

---

## Step 9 - Cleanup and Consistency

- [ ] Remove any remaining references to `tool_args["reasoning"]` or `tool_args["thinking_blocks"]`.
- [ ] Ensure `reasoning` is never placed in `tool_args` in any provider path.
- [ ] Confirm `preamble` is only on `AgentToolCall.preamble`.

**Verify**
- [ ] No new `tool_args` fields were added for reasoning/preamble.
- [ ] All tool calls still carry valid `completion` or `responses` data for history.

---

## Step 10 - Validation Pass

- [ ] Scan for any call sites still expecting `tool_args["reasoning"]` or `tool_args["thinking_blocks"]`.
- [ ] Confirm `tool_call` events include `reasoning` or `reasoning_ref` only when appropriate.
- [ ] Ensure `reasoning` is filtered for empty/whitespace blocks.

**Verify**
- [ ] No linting or type errors introduced.
- [ ] The new event type appears in SSE stream after a tool call.

---

## Post-Implementation Tests (Optional)

- [ ] Anthropic extended thinking (interleaved) produces per-tool reasoning events.
- [ ] OAI Responses streaming produces per-tool reasoning events.
- [ ] OAI Responses non-streaming produces per-tool reasoning events.
- [ ] Parallel tool calls produce `reasoning_ref` to the most recent reasoning call.
- [ ] Text-only responses emit `tool_call` with UUID and reasoning (if any).
