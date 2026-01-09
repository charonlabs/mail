# Message and Prompt Format in AI SDK

Based on search through `ai-sdk-llms.txt`.

## LanguageModelV3Prompt Structure

The prompt is composed of two main parts:

- **`system`** (string or array of system messages) - Instructions for the model
- **`messages`** (array of `LanguageModelV3Message`) - Conversation history

```typescript
const prompt = {
  system: "You are a helpful assistant.",
  messages: [
    { role: 'user', content: [...] },
    { role: 'assistant', content: [...] },
    { role: 'tool', content: [...] }
  ]
}
```

## Message Types and Roles

There are **4 main message roles**:

| Role | Purpose | When Used |
|------|---------|-----------|
| `user` | User input and follow-ups | Initial prompts, user responses |
| `assistant` | Model's responses and tool calls | After model generates output |
| `tool` | Tool execution results | After executing a tool, before next model call |
| `system` | System instructions/context | At the head of messages array (multiple allowed for cache control) |

## Message Structure with Content Parts

Each message has a `role` and `content` array containing **content parts**:

```typescript
{
  role: 'user' | 'assistant' | 'tool' | 'system',
  content: ContentPart[]  // Array of content parts
}
```

## Content Part Types

The `content` array can contain multiple part types:

### Text Part
```typescript
{
  type: 'text',
  text: string
}
```

### Image Part (multi-modal)
```typescript
{
  type: 'image',
  image: Buffer | string  // Base64 data or URL
}
// OR with file ID (OpenAI):
{
  type: 'image',
  image: 'file-8EFBcWHsQxZV7YGezBC1fq'
}
```

### PDF/File Part
```typescript
{
  type: 'file',
  data: Buffer,
  mediaType: 'application/pdf'  // or other MIME types
}
```

### Audio Part
```typescript
{
  type: 'audio',
  data: Buffer,
  mediaType: 'audio/mpeg'
}
```

### Tool Call Part (from assistant)
```typescript
{
  type: 'tool-call',
  toolCallId: string,
  toolName: string,
  input: Record<string, any>
}
```

### Tool Result Part (from tool message)
```typescript
{
  type: 'tool-result',
  toolCallId: string,
  toolName: string,
  output: string | Record<string, any>
}
```

### Tool Error Part
```typescript
{
  type: 'tool-error',
  toolCallId: string,
  toolName: string,
  error: string  // Error message from failed tool execution
}
```

### Multi-modal Tool Results (Anthropic experimental)
```typescript
{
  type: 'image' | 'text',
  data: Buffer,
  mediaType: string
}
```

## Complete Message Flow Example

```typescript
messages: [
  // User message with text + image
  {
    role: 'user',
    content: [
      { type: 'text', text: 'Please describe the image.' },
      { type: 'image', image: readFileSync('./image.png') }
    ]
  },
  // Assistant response with tool call
  {
    role: 'assistant',
    content: [
      {
        type: 'tool-call',
        toolCallId: 'call_123',
        toolName: 'get_weather',
        input: { location: 'Tokyo' }
      }
    ]
  },
  // Tool execution result
  {
    role: 'tool',
    content: [
      {
        type: 'tool-result',
        toolCallId: 'call_123',
        toolName: 'get_weather',
        output: { temperature: 22, conditions: 'sunny' }
      }
    ]
  },
  // (Model generates new response based on tool result)
]
```

## System Messages with Cache Control

Multiple system messages allowed at head of array for Anthropic cache control:

```typescript
messages: [
  {
    role: 'system',
    content: 'Cached system message part',
    providerOptions: {
      anthropic: { cacheControl: { type: 'ephemeral' } }
    }
  },
  {
    role: 'system',
    content: 'Uncached system message part'
  },
  {
    role: 'user',
    content: 'User prompt'
  }
]
```

## Image Content Variations

Images can be passed three ways:

```typescript
// 1. Buffer/Base64 data
{ type: 'image', image: Buffer.from(...) }

// 2. URL string
{ type: 'image', image: 'https://example.com/image.png' }

// 3. OpenAI file ID
{ type: 'image', image: 'file-8EFBcWHsQxZV7YGezBC1fq' }
```

## Multi-turn Tool Calling Flow

When `stopWhen` is configured:

1. Model generates `tool-call` content part
2. Tool is executed
3. Result added as `role: 'tool'` message with `tool-result` part
4. Model receives complete message history including tool result
5. Model generates next response (may call more tools or provide final answer)

This creates an **automatic multi-step agentic loop** without manual intervention.
