# Corrections Needed for MAIL AI SDK Provider Sketch

After validating against the full AI SDK documentation, here are the corrections needed for `mail-ai-sdk-provider-sketch.md` (see v2: `../mail-ai-sdk-provider-v2.md`).

**Verified Line References:**
- Lines 12780-12797: `doGenerate` return structure ✅
- Lines 12811-12839: `doStream` with text-start/delta/end, finish ✅
- Lines 7900-7992: All stream part types in fullStream ✅
- Lines 12075-12122: Middleware wrapStream with TransformStream ✅
- Line 11362: `specificationVersion: 'v3'` ✅
- Lines 9791-9794: Tool call structure with `input` (object, not string) ✅

## Critical Corrections

### 1. specificationVersion
**My sketch:**
```typescript
readonly specificationVersion = 'V3' as const;
```

**Correct:**
```typescript
readonly specificationVersion = 'v3';  // lowercase 'v', string value "v3"
```

### 2. Stream Part Types - Text Streaming
**My sketch:** Used single `type: 'text'` parts

**Correct:** Use `text-start`, `text-delta`, `text-end` sequence:
```typescript
{ type: 'text-start', id: 'text-1' }
{ type: 'text-delta', id: 'text-1', delta: 'Hello' }
{ type: 'text-delta', id: 'text-1', delta: ' world' }
{ type: 'text-end', id: 'text-1' }
```

Text parts require an `id` field and use `delta` not `text`.

### 3. Stream Start Event
**My sketch:** Used `type: 'stream-start'`

**Correct:** There's no `stream-start` type. Use `start` or simply begin with content:
```typescript
{ type: 'start' }  // If needed at all
```

### 4. No response-metadata Stream Part
**My sketch:**
```typescript
controller.enqueue({
  type: 'response-metadata',
  modelId: 'mail-swarm',
  headers: {},
});
```

**Correct:** There's no `response-metadata` stream part type. Remove this. Response metadata comes in the `doStream()` return value's `rest` object, not as a stream part.

### 5. finishReason Structure
**My sketch:** Used simple strings like `'stop'`, `'error'`, `'tool-calls'`

**Correct:** In V3, finishReason is an object:
```typescript
{
  type: 'finish',
  finishReason: { unified: 'stop', raw: undefined },
  // ...
}
```

**Note:** There's an inconsistency in docs - some examples (lines 8073, 8093) use simple strings `'stop'`, but the authoritative `MockLanguageModelV3` examples (lines 12782, 12821) use the object form. Use the object form for V3 compliance.

### 6. Usage Structure
**My sketch:**
```typescript
usage: {
  inputTokens: undefined,
  outputTokens: undefined,
  totalTokens: undefined,
}
```

**Correct:** V3 has nested usage structure:
```typescript
usage: {
  inputTokens: {
    total: 0,
    noCache: 0,
    cacheRead: undefined,
    cacheWrite: undefined,
  },
  outputTokens: {
    total: 0,
    text: 0,
    reasoning: undefined,
  },
}
```

### 7. Tool Call Stream Parts
**My sketch:** Used `toolCallType: 'function'` and `args: string`

**Correct:** Check exact fields - likely `toolName`, `toolCallId`, `input` (as object, not string):
```typescript
{
  type: 'tool-call',
  toolCallId: string,
  toolName: string,
  input: Record<string, any>  // Object, not JSON string
}
```

### 8. Reasoning Stream Parts
**My sketch:** Used `type: 'reasoning'` with `text` field

**Correct:** Use `reasoning-start`, `reasoning-delta`, `reasoning-end` sequence:
```typescript
{ type: 'reasoning-start', id: 'reasoning-1' }
{ type: 'reasoning-delta', id: 'reasoning-1', delta: 'thinking...' }
{ type: 'reasoning-end', id: 'reasoning-1' }
```

### 9. doGenerate Return Type
**My sketch:** Had `content` as array with tool calls embedded

**Correct:** Content is simpler, tool calls are separate:
```typescript
{
  content: Array<{ type: 'text'; text: string }>,  // Just text content
  finishReason: { unified: string; raw?: any },
  usage: { inputTokens: {...}, outputTokens: {...} },
  warnings?: Array<{ message: string }>,
}
```

### 10. Warnings Array
**My sketch:** Used `{ type: string; message: string }`

**Correct:** Warnings are simpler: `Array<{ message: string }>` (no `type` field visible in examples)

## Minor Adjustments

### Provider Metadata
My approach was correct - keyed by provider name (`mail`) with custom data. This is confirmed.

### Message/Prompt Handling
My message extraction approach was generally correct. The prompt structure has:
- `system`: string or array of system messages
- `messages`: array with `role` and `content` parts

Tool results use `type: 'tool-result'` with `output` field (not `result` as I may have used).

## Summary of Changes Needed

1. ✅ Fix `specificationVersion` to lowercase `'v3'`
2. ✅ Change text streaming to `text-start/delta/end` with `id` and `delta`
3. ✅ Remove fake `stream-start` and `response-metadata` types
4. ✅ Update `finishReason` to `{ unified: string, raw?: any }` structure
5. ✅ Update `usage` to nested `{ inputTokens: {...}, outputTokens: {...} }` structure
6. ✅ Fix tool calls to use `input` as object (not JSON string `args`)
7. ✅ Change reasoning to `reasoning-start/delta/end` sequence
8. ✅ Fix warning structure to `{ message: string }`

These are mostly structural changes to match the exact V3 spec - the overall architecture and approach is sound.
