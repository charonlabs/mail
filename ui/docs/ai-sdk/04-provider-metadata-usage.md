# Provider Metadata, Response Metadata, and Usage Information

Based on search through `ai-sdk-llms.txt`.

## How providerMetadata Works

**Yes, providers can add custom metadata.** The `providerMetadata` structure is **provider-agnostic**:

- **Structure**: The outer key is the provider name (e.g., `openai`, `google`)
- **Access pattern**: `providerMetadata?.{providerName}.{metadata}`
- **Examples from the docs**:

```typescript
// Google provider with grounding metadata
const { text, sources, providerMetadata } = await generateText({
  model: google('gemini-3-pro-preview'),
  // ...
});
const metadata = providerMetadata?.google as GoogleGenerativeAIProviderMetadata;
const groundingMetadata = metadata?.groundingMetadata;
const safetyRatings = metadata?.safetyRatings;

// OpenAI with response IDs (for Responses API)
const result1 = await generateText({
  model: openai.responses('gpt-4o-mini'),
  // ...
});
const result2 = await generateText({
  // ...
  providerOptions: {
    openai: {
      previousResponseId: result1.providerMetadata?.openai.responseId as string,
    },
  },
});

// OpenAI with image generation
const { image, providerMetadata } = await generateImage({
  model: openai.image('dall-e-3'),
  // ...
});
const revisedPrompt = providerMetadata.openai.images[0]?.revisedPrompt;
```

**Key insight**: Provider metadata for image generation includes an `images` array that always has the same length as the top-level `images` key.

## Response Metadata Structure

The response includes multiple types of metadata:

```typescript
interface GenerateTextResult {
  text: string;
  reasoning?: string;              // Full reasoning from model
  reasoningText?: string;           // Reasoning text (some models only)
  files?: any[];                    // Generated files
  sources?: Source[];               // References used (some models)
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
  finishReason: string;             // Unified finish reason
  rawFinishReason?: string;         // Raw reason from provider
  usage: UsageInfo;                 // This step's usage
  totalUsage?: UsageInfo;           // Cumulative across all steps
  warnings?: Warning[];             // Provider warnings
  request?: Record<string, any>;    // Request info
  response?: {
    headers?: Record<string, string>;
    body?: any;
    messages?: Message[];           // Generated messages
  };
  providerMetadata?: Record<string, any>;  // Provider-specific data
  steps?: StepInfo[];               // Intermediate steps
}
```

**Source structure** (from docs):
```typescript
interface Source {
  id: string;
  url: string;
  title?: string;
  sourceType: 'url';
  providerMetadata?: Record<string, any>;  // Provider-specific source metadata
}
```

## Finish Reasons

**There are two finish reason fields:**

1. **`finishReason`** - Unified/normalized reason (AI SDK standardized)
2. **`rawFinishReason`** - Raw reason directly from the provider

**Valid finish reason values mentioned in docs:**
- `'stop'` - Normal completion (most common)
- `'tool-calls'` - Model generated tool calls (in multi-step scenarios)
- `'length'` - Model hit max token limit
- Other potential values implied but not explicitly listed

**From test mock examples**, the structure is:
```typescript
finishReason: { unified: 'stop', raw: undefined }  // For newer mock format
// OR (older format)
finishReason: 'stop'  // Simple string
```

**Context from docs**: "A finish reasoning other than tool-calls is returned" suggests `tool-calls` is a distinct state checked during agent loop control.

## Token Usage Reporting

**Two levels of usage tracking exist:**

**Step-level usage**:
```typescript
interface Usage {
  inputTokens: {
    total: number;
    noCache?: number;        // Tokens without cache hit
    cacheRead?: number;      // Tokens from cache read
    cacheWrite?: number;     // Tokens written to cache
  };
  outputTokens: {
    total: number;
    text?: number;           // Text tokens
    reasoning?: number;      // Extended thinking tokens
  };
}
```

**Summary from docs** (older format, simpler):
```typescript
usage: {
  completionTokens: number;  // Output tokens
  promptTokens: number;      // Input tokens
  totalTokens?: number;
}
```

**Aggregation across steps**:
```typescript
const { totalUsage } = await generateText({ /* ... */ });
// Accumulates input/output across all steps in multi-step calls

// Example aggregation pattern from docs:
const totalUsage = steps.reduce(
  (acc, step) => ({
    inputTokens: acc.inputTokens + (step.usage?.inputTokens?.total ?? 0),
    outputTokens: acc.outputTokens + (step.usage?.outputTokens?.total ?? 0),
  }),
  { inputTokens: 0, outputTokens: 0 }
);
```

**Cost calculation example**:
```typescript
const costInDollars =
  (totalUsage.inputTokens * 0.01 + totalUsage.outputTokens * 0.03) / 1000;
```

**Provider-specific usage**: OpenAI exposes cached tokens:
```typescript
cachedPromptTokens: providerMetadata?.openai?.cachedPromptTokens
```

## Key Takeaway

The AI SDK separates unified (normalized across providers) from raw (provider-specific) data, allowing code portability while still providing access to provider-specific details through `providerMetadata`.
