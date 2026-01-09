# LanguageModelV3 Interface Definition

Based on thorough search of `ai-sdk-llms.txt`.

## LanguageModelV3 Required Properties

The LanguageModelV3 specification requires these core properties:

1. **`specificationVersion`**: `"v3"` - Identifies the specification version
2. **`modelId`**: `string` - The unique identifier for the model (e.g., "claude-opus-4-5-20251101")
3. **`provider`**: `string` - The provider name (e.g., "anthropic", "openai")

## Core Methods

### doGenerate()

**Method Signature:**
```typescript
async doGenerate(options?: LanguageModelV3Options): Promise<LanguageModelV3GenerateResult>
```

**Return Type:**
```typescript
{
  // Content blocks produced by the model
  content: Array<{
    type: 'text';
    text: string
  }>;

  // Why the model stopped generating
  finishReason: {
    unified: 'stop' | 'length' | 'content-filter' | 'tool-calls' | 'error' | 'other';
    raw?: any;
  };

  // Token usage information
  usage: {
    inputTokens: {
      total: number;
      noCache: number;
      cacheRead?: number;
      cacheWrite?: number;
    };
    outputTokens: {
      total: number;
      text: number;
      reasoning?: number;
    };
  };

  // Any warnings from the model
  warnings?: Array<{ message: string }>;
}
```

### doStream()

**Method Signature:**
```typescript
async doStream(options?: LanguageModelV3Options): Promise<LanguageModelV3StreamResult>
```

**Return Type:**
```typescript
{
  // Readable stream of incremental chunks
  stream: ReadableStream<LanguageModelV3StreamPart>;

  // Additional metadata
  rawCall?: { url: string; headers: Record<string, string> };
}
```

**Stream Chunk Types:**
```typescript
type LanguageModelV3StreamPart =
  | { type: 'text-start'; id: string }
  | { type: 'text-delta'; id: string; delta: string }
  | { type: 'text-end'; id: string }
  | {
      type: 'finish';
      finishReason: { unified: string; raw?: any };
      logprobs?: any;
      usage: {
        inputTokens: { total: number; noCache: number; cacheRead?: number; cacheWrite?: number };
        outputTokens: { total: number; text: number; reasoning?: number };
      };
    }
```

## Middleware Integration

Middleware wrapping requires implementing **`LanguageModelV3Middleware`** with three optional functions:

```typescript
interface LanguageModelV3Middleware {
  // Transform parameters before passing to model
  transformParams?: async (options: {
    params: LanguageModelV3Parameters;
  }) => LanguageModelV3Parameters;

  // Wrap doGenerate method
  wrapGenerate?: async (options: {
    doGenerate: () => Promise<LanguageModelV3GenerateResult>;
    params: LanguageModelV3Parameters;
  }) => Promise<LanguageModelV3GenerateResult>;

  // Wrap doStream method
  wrapStream?: async (options: {
    doStream: () => Promise<LanguageModelV3StreamResult>;
    params: LanguageModelV3Parameters;
  }) => Promise<LanguageModelV3StreamResult>;
}
```

## Key Documentation References

The interface specification is documented at:
- **Source**: https://github.com/vercel/ai/blob/main/packages/provider/src/language-model/v3/language-model-v3.ts
- **Examples**: MockLanguageModelV3 test helpers in `ai/test` package (lines 12759-12922 of the documentation)

## Usage Examples from Documentation

**doGenerate Example (lines 12780-12797):**
```typescript
doGenerate: async () => ({
  content: [{ type: 'text', text: `Hello, world!` }],
  finishReason: { unified: 'stop', raw: undefined },
  usage: {
    inputTokens: {
      total: 10,
      noCache: 10,
      cacheRead: undefined,
      cacheWrite: undefined,
    },
    outputTokens: {
      total: 20,
      text: 20,
      reasoning: undefined,
    },
  },
  warnings: [],
})
```

**doStream Example (lines 12811-12839):**
```typescript
doStream: async () => ({
  stream: simulateReadableStream({
    chunks: [
      { type: 'text-start', id: 'text-1' },
      { type: 'text-delta', id: 'text-1', delta: 'Hello' },
      { type: 'text-delta', id: 'text-1', delta: ', ' },
      { type: 'text-delta', id: 'text-1', delta: 'world!' },
      { type: 'text-end', id: 'text-1' },
      {
        type: 'finish',
        finishReason: { unified: 'stop', raw: undefined },
        logprobs: undefined,
        usage: { /* ... */ },
      },
    ],
  }),
})
```
