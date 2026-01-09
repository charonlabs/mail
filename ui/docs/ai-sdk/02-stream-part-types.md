# Stream Part Types and Format

Based on search through `ai-sdk-llms.txt`.

## All Valid Stream Part Types

The documentation defines the following stream part types (from fullStream iteration, lines 7900-7992):

| Type | Category | Purpose |
|------|----------|---------|
| `start` | Lifecycle | Stream initialization |
| `start-step` | Lifecycle | Start of a processing step |
| `text-start` | Text | Beginning of text content |
| `text-delta` | Text | Incremental text chunk |
| `text-end` | Text | End of text content |
| `reasoning-start` | Reasoning | Beginning of extended thinking |
| `reasoning-delta` | Reasoning | Incremental reasoning chunk |
| `reasoning-end` | Reasoning | End of reasoning content |
| `source` | Metadata | Source/citation information |
| `file` | Metadata | File reference |
| `tool-call` | Tool | Tool invocation |
| `tool-input-start` | Tool | Beginning of tool input |
| `tool-input-delta` | Tool | Incremental tool input |
| `tool-input-end` | Tool | End of tool input |
| `tool-result` | Tool | Tool execution result |
| `tool-error` | Tool | Tool execution error |
| `finish-step` | Lifecycle | End of processing step |
| `finish` | Lifecycle | Stream completion |
| `error` | Error | Error event |
| `raw` | Raw | Raw/unprocessed value |

## Exact Format/Structure of Each Stream Part

### Text Streaming Parts (lines 12814-12821)

```typescript
// text-start
{ type: 'text-start', id: 'text-1' }

// text-delta
{ type: 'text-delta', id: 'text-1', delta: 'Hello' }
{ type: 'text-delta', id: 'text-1', delta: ', ' }
{ type: 'text-delta', id: 'text-1', delta: 'world!' }

// text-end
{ type: 'text-end', id: 'text-1' }
```

**Properties:**
- `id`: String identifier for the text block
- `delta`: String - the incremental text content (only for text-delta)

### Finish Part (lines 12819-12836)

```typescript
{
  type: 'finish',
  finishReason: { unified: 'stop', raw: undefined },
  logprobs: undefined,
  usage: {
    inputTokens: {
      total: 3,
      noCache: 3,
      cacheRead: undefined,
      cacheWrite: undefined,
    },
    outputTokens: {
      total: 10,
      text: 10,
      reasoning: undefined,
    },
  },
}
```

**Properties:**
- `finishReason`: Object with `{ unified: string, raw?: string }`
- `logprobs`: Optional log probabilities
- `usage`: Token usage breakdown with `inputTokens` and `outputTokens`

### Finish-Step Part (lines 8070-8088)

```typescript
{
  type: 'finish-step',
  finishReason: 'stop',
  logprobs: undefined,
  usage: {
    completionTokens: NaN,
    promptTokens: NaN,
    totalTokens: NaN,
  },
  request: {},
  response: {
    id: 'response-id',
    modelId: 'mock-model-id',
    timestamp: new Date(0),
  },
  warnings: [],
  isContinued: false,
}
```

**Properties:**
- `finishReason`: String reason for step completion
- `usage`: Token counts
- `request`: Request metadata
- `response`: Response metadata with id, modelId, timestamp
- `warnings`: Array of warnings
- `isContinued`: Boolean indicating if step continues

### Tool Call Parts (lines 7942-7970)

```typescript
case 'tool-call': {
  // part.toolName is available
  switch (part.toolName) {
    case 'cityAttractions': {
      // handle tool call here
    }
  }
}

case 'tool-input-start': {
  // handle tool input start
}

case 'tool-input-delta': {
  // handle tool input delta
}

case 'tool-input-end': {
  // handle tool input end
}

case 'tool-result': {
  // part.toolName is available
  switch (part.toolName) {
    case 'cityAttractions': {
      // handle tool result here
    }
  }
}
```

**Properties:**
- `toolName`: String - name of the tool (for tool-call, tool-input-*, tool-result, tool-error)
- `delta`: String (for tool-input-delta)
- `id`: String identifier for tool input (inferred from context)

### Reasoning Parts (lines 7922-7932)

```typescript
case 'reasoning-start': {
  // handle reasoning start
}

case 'reasoning-delta': {
  // handle reasoning delta here
}

case 'reasoning-end': {
  // handle reasoning end
}
```

**Properties:**
- `delta`: String (for reasoning-delta, inferred from onChunk pattern)
- `id`: String identifier (inferred)

### Other Parts

```typescript
case 'source': {
  // handle source here
}

case 'file': {
  // handle file here
}

case 'error': {
  // handle error here
}

case 'raw': {
  // handle raw value
}
```

## How Stream Parts Are Yielded from doStream()

From the middleware example (lines 12075-12122):

```typescript
wrapStream: async ({ doStream, params }) => {
  // Call doStream() to get the stream
  const { stream, ...rest } = await doStream();

  // stream is a ReadableStream<LanguageModelV3StreamPart>
  // Create a TransformStream to process chunks
  const transformStream = new TransformStream<
    LanguageModelV3StreamPart,
    LanguageModelV3StreamPart
  >({
    transform(chunk, controller) {
      // Process each chunk
      switch (chunk.type) {
        case 'text-delta': {
          // Accumulate text
          break;
        }
      }
      // Enqueue the processed chunk
      controller.enqueue(chunk);
    },

    flush() {
      // Called when stream finishes
      console.log('doStream finished');
    },
  });

  // Return the piped stream
  return {
    stream: stream.pipeThrough(transformStream),
    ...rest,
  };
}
```

**Flow:**
1. `doStream()` is called and returns `{ stream, ...rest }` where stream is a `ReadableStream<LanguageModelV3StreamPart>`
2. Chunks are yielded sequentially from the stream
3. Each chunk has a `type` property that identifies which stream part it is
4. The stream ends when all parts including the final `finish` part are yielded

## The "Controller" Object and Its Methods

From lines 8034-8042 (TransformStream example):

```typescript
new TransformStream<TextStreamPart<TOOLS>, TextStreamPart<TOOLS>>({
  transform(chunk, controller) {
    controller.enqueue(
      chunk.type === 'text'
        ? { ...chunk, text: chunk.text.toUpperCase() }
        : chunk,
    );
  },
})
```

**Controller is a `TransformStreamDefaultController` with these methods:**

| Method | Purpose | Example |
|--------|---------|---------|
| `enqueue(chunk)` | Add a chunk to the output stream | `controller.enqueue(chunk)` |
| `terminate()` | End the stream (implicit in transform) | Called automatically |
| `error(error)` | Signal an error | `controller.error(new Error('msg'))` |

**Key Method Details:**

- **`controller.enqueue(chunk)`** (lines 8035, 8062, 8071, 8091, 8110, 12109)
  - Adds a processed chunk to the output stream
  - Accepts any value of the output type (LanguageModelV3StreamPart)
  - Can be called multiple times per transform() invocation
  - Can yield modified versions of the input chunk

**Transforming Chunks (lines 8034-8041):**
```typescript
controller.enqueue(
  chunk.type === 'text'
    ? { ...chunk, text: chunk.text.toUpperCase() }
    : chunk,
);
```
Shows you can modify properties before enqueuing.

**Simulating Events When Stopping (lines 8071-8093):**
```typescript
// Must enqueue finish-step when stopping
controller.enqueue({
  type: 'finish-step',
  finishReason: 'stop',
  // ... properties
});

// Must enqueue finish to mark stream end
controller.enqueue({
  type: 'finish',
  finishReason: 'stop',
  // ... properties
});
```

**The flush() Callback (line 12112):**
```typescript
flush() {
  // Called when the source stream closes
  // Useful for cleanup and final logging
  console.log('doStream finished');
}
```

## Additional Streaming Details

**Event Stream Format (lines 12941-12949)** - SSE representation:
```
data: {"type":"text-delta","id":"text-1","delta":"This"}\n\n
data: {"type":"text-delta","id":"text-1","delta":" is an"}\n\n
data: {"type":"text-delta","id":"text-1","delta":" example."}\n\n
data: {"type":"finish"}\n\n
data: [DONE]\n\n
```

**doStream() Return Value (line 12079):**
```typescript
const { stream, ...rest } = await doStream();
// stream: ReadableStream<LanguageModelV3StreamPart>
// rest: Additional metadata (finishReason, usage, response, etc.)
```

## Summary Table: Stream Part Properties

| Part Type | Required Properties | Optional Properties |
|-----------|-------------------|-------------------|
| text-delta | type, id, delta | - |
| text-start | type, id | - |
| text-end | type, id | - |
| reasoning-delta | type, id, delta | - |
| reasoning-start | type, id | - |
| reasoning-end | type, id | - |
| tool-call | type, toolName | - |
| tool-input-delta | type, toolName, delta, id | - |
| tool-input-start | type, toolName, id | - |
| tool-input-end | type, toolName, id | - |
| tool-result | type, toolName | - |
| tool-error | type, toolName | - |
| finish | type | finishReason, logprobs, usage |
| finish-step | type, finishReason | logprobs, usage, request, response, warnings, isContinued |
| start | type | - |
| start-step | type | - |
| source | type | - |
| file | type | - |
| error | type | - |
| raw | type | - |

All stream parts are of type `LanguageModelV3StreamPart` (as defined in `@ai-sdk/provider`).
