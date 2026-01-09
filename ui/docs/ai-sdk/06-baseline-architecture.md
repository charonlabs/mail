# AI SDK Baseline Architecture

Verified from AI SDK overview and Next.js getting started docs in `ai-sdk-llms.txt`.

## SDK Structure

```
ai (main package)
├── AI SDK Core         - Server-side generation functions
│   ├── generateText    - Non-interactive text generation
│   ├── streamText      - Streaming text generation
│   ├── generateObject  - Structured data (Zod schema)
│   └── streamObject    - Streaming structured data
│
├── AI SDK UI           - Client-side hooks
│   ├── useChat         - Chat interface hook
│   ├── useCompletion   - Text completion hook
│   ├── useObject       - Streamed JSON objects
│   └── useAssistant    - OpenAI Assistant API
│
└── Provider Packages   - Model integrations
    ├── @ai-sdk/openai
    ├── @ai-sdk/anthropic
    ├── @ai-sdk/google
    └── ... (or custom LanguageModelV3)
```

## Standard Next.js Pattern (lines 481-535)

**Route Handler** (`app/api/chat/route.ts`):
```typescript
import { convertToModelMessages, streamText, UIMessage } from 'ai';

export const maxDuration = 30;

export async function POST(req: Request) {
  const { messages }: { messages: UIMessage[] } = await req.json();

  const result = streamText({
    model: 'openai/gpt-4o',  // or provider function
    messages: await convertToModelMessages(messages),
    system: 'Optional system prompt',
  });

  return result.toUIMessageStreamResponse();
}
```

**Client** (`app/page.tsx`):
```typescript
'use client';
import { useChat } from '@ai-sdk/react';

export default function Chat() {
  const { messages, sendMessage } = useChat();
  // ...
}
```

## Key Functions

| Function | Import | Purpose |
|----------|--------|---------|
| `streamText` | `ai` | Core streaming generation |
| `generateText` | `ai` | Non-streaming generation |
| `convertToModelMessages` | `ai` | UIMessage[] → Model format |
| `tool()` | `ai` | Define tools with Zod schemas |
| `useChat` | `@ai-sdk/react` | Client-side chat hook |

## Data Flow

```
Client (useChat)
    │
    ▼ POST { messages: UIMessage[] }

Route Handler
    │
    ├── convertToModelMessages(messages)
    │
    ├── streamText({ model, messages, tools? })
    │       │
    │       ▼ Calls provider's doStream()
    │       Returns LanguageModelV3StreamPart[]
    │
    └── result.toUIMessageStreamResponse()
            │
            ▼ Converts to UI Message Stream format

    SSE Response
    │
    ▼ data: {"type":"text-delta","id":"...","delta":"..."}\n\n

Client (useChat) receives and parses stream
```

## UI Message Stream Format (lines 12940-12948)

The SSE format that `useChat` expects:

```
data: {"type":"start","messageId":"msg-123"}\n\n
data: {"type":"text-start","id":"text-1"}\n\n
data: {"type":"text-delta","id":"text-1","delta":"This"}\n\n
data: {"type":"text-delta","id":"text-1","delta":" is an"}\n\n
data: {"type":"text-delta","id":"text-1","delta":" example."}\n\n
data: {"type":"text-end","id":"text-1"}\n\n
data: {"type":"finish"}\n\n
data: [DONE]\n\n
```

Required header: `x-vercel-ai-ui-message-stream: v1`

## Provider Types (lines 2725-2729)

Models can be specified as:
1. **String ID** (with gateway): `'openai/gpt-4o'`, `'anthropic/claude-sonnet-4'`
2. **Provider function**: `google('gemini-3-pro-preview')`, `openai('gpt-5')`
3. **Custom LanguageModelV3**: Implement `doGenerate()` and `doStream()`

## Result Properties (lines 7679-7697)

`generateText` / `streamText` return:
- `text`, `reasoning`, `reasoningText`
- `files`, `sources`
- `toolCalls`, `toolResults`
- `finishReason`, `rawFinishReason`
- `usage`, `totalUsage`
- `warnings`, `request`, `response`
- `providerMetadata` - Custom provider data (keyed by provider name)
- `steps` - For multi-step generations

## streamText Helper Methods (lines 7773-7776)

- `toUIMessageStreamResponse()` - UI Message stream HTTP response
- `pipeUIMessageStreamToResponse()` - Pipe to Node.js response
- `toTextStreamResponse()` - Simple text stream
- `pipeTextStreamToResponse()` - Text to Node.js response

## Key Insight for MAIL Provider

The `toUIMessageStreamResponse()` method converts `LanguageModelV3StreamPart[]` from `doStream()` into the UI Message Stream format. So our MAIL provider just needs to:

1. Implement `doStream()` returning `LanguageModelV3StreamPart[]`
2. Let the SDK handle conversion to UI Message Stream
3. `useChat` on the client handles the rest

We don't need to implement the SSE format ourselves - the SDK does that conversion.
