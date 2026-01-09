# AI SDK Deep Dive - Complete Overview

A comprehensive reference for implementing the MAIL AI SDK provider, compiled from the full AI SDK documentation.

---

## What is the AI SDK?

The AI SDK is Vercel's TypeScript toolkit for building AI applications. It provides:

1. **Unified API** - Same interface across all LLM providers (OpenAI, Anthropic, Google, etc.)
2. **Streaming-first** - Built for real-time, interactive experiences
3. **Framework integrations** - Works with Next.js, React, Vue, Svelte, Node.js
4. **Rich output support** - Text, structured data (JSON), tool calls, file generation

---

## Three Layers of the SDK

### Layer 1: AI SDK Core (`ai` package)

Server-side functions for interacting with LLMs:

| Function | Purpose | Use Case |
|----------|---------|----------|
| `generateText` | Non-streaming text | Automation, batch processing, agents |
| `streamText` | Streaming text | Chatbots, real-time UI |
| `generateObject` | Structured JSON (Zod) | Data extraction, classification |
| `streamObject` | Streaming JSON | Generative UI |

All functions accept a **model** and return a **result object** with rich metadata.

### Layer 2: AI SDK UI (`@ai-sdk/react`, etc.)

Client-side hooks for building UIs:

| Hook | Purpose |
|------|---------|
| `useChat` | Full chat interface with message history |
| `useCompletion` | Simple text completion |
| `useObject` | Streaming JSON objects |
| `useAssistant` | OpenAI Assistant API |

Hooks connect to API routes and handle streaming automatically.

### Layer 3: Providers (`@ai-sdk/openai`, `@ai-sdk/anthropic`, etc.)

Model integrations implementing `LanguageModelV3`:

```typescript
// Usage examples
import { openai } from '@ai-sdk/openai';
import { anthropic } from '@ai-sdk/anthropic';

streamText({ model: openai('gpt-5') });
streamText({ model: anthropic('claude-sonnet-4') });
streamText({ model: 'gateway/openai/gpt-5' });  // String ID with gateway
```

---

## The LanguageModelV3 Interface

Custom providers must implement this interface:

```typescript
interface LanguageModelV3 {
  // Required properties
  readonly specificationVersion: 'v3';
  readonly provider: string;
  readonly modelId: string;

  // Required methods
  doGenerate(options: LanguageModelV3CallOptions): Promise<LanguageModelV3GenerateResult>;
  doStream(options: LanguageModelV3CallOptions): Promise<LanguageModelV3StreamResult>;
}
```

### doGenerate() Return Type

```typescript
{
  content: Array<{ type: 'text'; text: string }>;
  finishReason: {
    unified: 'stop' | 'length' | 'content-filter' | 'tool-calls' | 'error' | 'other';
    raw?: any;
  };
  usage: {
    inputTokens: { total: number; noCache: number; cacheRead?: number; cacheWrite?: number };
    outputTokens: { total: number; text: number; reasoning?: number };
  };
  warnings?: Array<{ message: string }>;
}
```

### doStream() Return Type

```typescript
{
  stream: ReadableStream<LanguageModelV3StreamPart>;
  rawCall?: { url: string; headers: Record<string, string> };
}
```

---

## Stream Part Types

The `doStream()` method yields these stream parts:

### Text Streaming
```typescript
{ type: 'text-start', id: 'text-1' }
{ type: 'text-delta', id: 'text-1', delta: 'Hello' }
{ type: 'text-delta', id: 'text-1', delta: ' world' }
{ type: 'text-end', id: 'text-1' }
```

### Reasoning (Extended Thinking)
```typescript
{ type: 'reasoning-start', id: 'reasoning-1' }
{ type: 'reasoning-delta', id: 'reasoning-1', delta: 'thinking...' }
{ type: 'reasoning-end', id: 'reasoning-1' }
```

### Tool Calls
```typescript
{ type: 'tool-call', toolCallId: 'call_123', toolName: 'get_weather', input: { city: 'Tokyo' } }
{ type: 'tool-input-start', toolName: 'get_weather', id: 'input-1' }
{ type: 'tool-input-delta', toolName: 'get_weather', id: 'input-1', delta: '{"city' }
{ type: 'tool-input-end', toolName: 'get_weather', id: 'input-1' }
{ type: 'tool-result', toolName: 'get_weather', toolCallId: 'call_123' }
{ type: 'tool-error', toolName: 'get_weather', toolCallId: 'call_123' }
```

### Lifecycle
```typescript
{ type: 'start' }
{ type: 'start-step' }
{ type: 'finish-step', finishReason: 'stop', usage: {...}, ... }
{ type: 'finish', finishReason: { unified: 'stop', raw: undefined }, usage: {...} }
```

### Other
```typescript
{ type: 'source', ... }    // Citations
{ type: 'file', ... }      // Generated files
{ type: 'error', ... }     // Errors
{ type: 'raw', ... }       // Raw provider data
```

---

## Provider Metadata

Providers can expose custom data via `providerMetadata`:

```typescript
// In doStream() or doGenerate()
return {
  // ... standard fields
  providerMetadata: {
    mail: {
      taskId: 'task-123',
      agentTrace: [...],
      currentAgent: 'supervisor'
    }
  }
};

// Client access
const result = await streamText({ model: mail('swarm') });
const metadata = await result.providerMetadata;
console.log(metadata?.mail?.taskId);
```

Key is the provider name (`mail`, `openai`, `google`, etc.).

---

## Next.js Integration Pattern

### Route Handler (`app/api/chat/route.ts`)

```typescript
import { convertToModelMessages, streamText, UIMessage } from 'ai';
import { mail } from '@mail/ai-sdk-provider';

export const maxDuration = 30;

export async function POST(req: Request) {
  const { messages }: { messages: UIMessage[] } = await req.json();

  const result = streamText({
    model: mail('research-swarm'),
    messages: await convertToModelMessages(messages),
    system: 'You are a helpful research assistant.',
  });

  return result.toUIMessageStreamResponse();
}
```

### Client Component (`app/page.tsx`)

```typescript
'use client';
import { useChat } from '@ai-sdk/react';

export default function Chat() {
  const { messages, sendMessage, input, setInput } = useChat();

  return (
    <div>
      {messages.map(m => (
        <div key={m.id}>
          {m.parts.map((part, i) =>
            part.type === 'text' && <span key={i}>{part.text}</span>
          )}
        </div>
      ))}
      <form onSubmit={e => { e.preventDefault(); sendMessage({ text: input }); setInput(''); }}>
        <input value={input} onChange={e => setInput(e.target.value)} />
      </form>
    </div>
  );
}
```

---

## UI Message Stream (Wire Format)

The SDK converts `LanguageModelV3StreamPart[]` to this SSE format:

```
data: {"type":"start","messageId":"msg-123"}\n\n
data: {"type":"text-start","id":"text-1"}\n\n
data: {"type":"text-delta","id":"text-1","delta":"Hello"}\n\n
data: {"type":"text-delta","id":"text-1","delta":" world"}\n\n
data: {"type":"text-end","id":"text-1"}\n\n
data: {"type":"finish"}\n\n
data: [DONE]\n\n
```

**You don't implement this** - `toUIMessageStreamResponse()` handles the conversion.

---

## Tool Handling

### Defining Tools

```typescript
import { tool } from 'ai';
import { z } from 'zod';

const result = await streamText({
  model: openai('gpt-5'),
  tools: {
    get_weather: tool({
      description: 'Get weather for a location',
      inputSchema: z.object({
        city: z.string().describe('City name'),
      }),
      execute: async ({ city }) => {
        return { temperature: 22, conditions: 'sunny' };
      },
    }),
  },
  stopWhen: stepCountIs(5),  // Enable multi-step tool calling
});
```

### Tool Call Flow

1. Model returns `finishReason: { unified: 'tool-calls' }`
2. SDK executes tool's `execute()` function
3. Tool result appended to messages
4. Model called again with result
5. Repeat until `stop` or step limit

### Tool Result Message Format

```typescript
{
  role: 'tool',
  content: [{
    type: 'tool-result',
    toolCallId: 'call_123',
    toolName: 'get_weather',
    output: { temperature: 22, conditions: 'sunny' }
  }]
}
```

---

## Message Format

### Prompt Structure

```typescript
{
  system: 'You are a helpful assistant.',
  messages: [
    { role: 'user', content: [{ type: 'text', text: 'Hello' }] },
    { role: 'assistant', content: [{ type: 'text', text: 'Hi there!' }] },
    { role: 'tool', content: [{ type: 'tool-result', ... }] }
  ]
}
```

### Content Part Types

- `{ type: 'text', text: string }` - Text content
- `{ type: 'image', image: Buffer | string }` - Image (base64 or URL)
- `{ type: 'file', data: Buffer, mediaType: string }` - Files (PDF, etc.)
- `{ type: 'tool-call', toolCallId, toolName, input }` - Tool invocation
- `{ type: 'tool-result', toolCallId, toolName, output }` - Tool result
- `{ type: 'tool-error', toolCallId, toolName, error }` - Tool error

---

## Result Object Properties

Both `generateText` and `streamText` return:

| Property | Description |
|----------|-------------|
| `text` | Generated text |
| `reasoning` | Extended thinking (if enabled) |
| `reasoningText` | Reasoning as plain text |
| `toolCalls` | Tool calls from last step |
| `toolResults` | Tool results from last step |
| `finishReason` | Why generation stopped |
| `rawFinishReason` | Provider's raw finish reason |
| `usage` | Token usage for last step |
| `totalUsage` | Cumulative usage across all steps |
| `warnings` | Provider warnings |
| `providerMetadata` | Custom provider data |
| `steps` | All steps in multi-step generation |
| `files` | Generated files |
| `sources` | Source citations |

---

## Finish Reasons

| Reason | Meaning |
|--------|---------|
| `stop` | Normal completion |
| `length` | Hit max tokens |
| `tool-calls` | Model wants to call tools |
| `content-filter` | Content filtered |
| `error` | Error occurred |
| `other` | Other reason |

---

## Usage Tracking

```typescript
const result = await generateText({ ... });

// Per-step usage
console.log(result.usage.inputTokens.total);
console.log(result.usage.outputTokens.total);

// With cache info
console.log(result.usage.inputTokens.cacheRead);   // Cached tokens
console.log(result.usage.inputTokens.cacheWrite);  // New cache

// Reasoning tokens
console.log(result.usage.outputTokens.reasoning);

// Multi-step total
console.log(result.totalUsage);
```

---

## Key Takeaways for MAIL Provider

1. **Implement LanguageModelV3** with `doGenerate()` and `doStream()`

2. **Use proper stream part types**:
   - `text-start` → `text-delta` → `text-end` (not just `text`)
   - Include `id` on all text parts
   - Use `delta` for content (not `text`)

3. **finishReason is an object**: `{ unified: 'stop', raw: undefined }`

4. **Usage is nested**: `{ inputTokens: { total, noCache, ... }, outputTokens: { total, text, ... } }`

5. **providerMetadata key is provider name**: `providerMetadata.mail.taskId`

6. **Let SDK handle SSE conversion**: Just return stream parts, `toUIMessageStreamResponse()` does the rest

7. **Tool calls use `input` (object)**: Not `args` (string)

---

## File References

| Topic | Lines in ai-sdk-llms.txt |
|-------|--------------------------|
| Core functions overview | 7602-7630 |
| generateText details | 7648-7737 |
| streamText details | 7738-7800 |
| Stream part types | 7900-7992 |
| Tool handling | 8877-8878, 9788-9813 |
| MockLanguageModelV3 examples | 12759-12922 |
| UI Message Stream format | 12940-12948 |
| Middleware | 12075-12122 |
