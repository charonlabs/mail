# MAIL AI SDK Provider - Implementation Sketch v2

> **Updated based on verified AI SDK documentation in `docs/ai-sdk/`**

## Overview

This provider wraps MAIL's multi-agent runtime as an AI SDK `LanguageModelV3`, enabling:
- `streamText()` / `generateText()` with MAIL swarms
- Tool calls mapped to MAIL actions
- Rich provider metadata exposing agent topology and events
- Task continuation via conversation history

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      AI SDK Application                      │
│  const response = await streamText({                        │
│    model: mail('research-swarm'),                           │
│    prompt: 'Research quantum computing',                    │
│  });                                                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    @mail/ai-sdk-provider                     │
│                                                              │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │ MAILLanguageModel│    │      Stream Transformer         │ │
│  │                 │    │                                 │ │
│  │ doGenerate()   │───▶│  MAIL SSE → LanguageModelV3     │ │
│  │ doStream()     │    │              StreamPart          │ │
│  └─────────────────┘    └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      MAIL Server                             │
│                                                              │
│  POST /ui/message { body, stream: true, task_id, ... }      │
│                              │                               │
│                              ▼                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Agent Swarm                           ││
│  │  Supervisor ──▶ Researcher ──▶ Writer ──▶ ...           ││
│  └─────────────────────────────────────────────────────────┘│
│                              │                               │
│                              ▼                               │
│  SSE Stream: new_message, tool_call, task_complete, etc.    │
└─────────────────────────────────────────────────────────────┘
```

## Event Mapping

| MAIL SSE Event | AI SDK Stream Part | Notes |
|----------------|-------------------|-------|
| `new_message` (broadcast_complete) | `text-start` → `text-delta` → `text-end` | Final response |
| `new_message` (agent→agent) | `text-delta` (optional) | Agent chatter if enabled |
| `tool_call` / `action_call` | `tool-call` | With `toolCallId`, `toolName`, `input` |
| `action_complete` | Update providerMetadata | Action result |
| `task_complete` | `finish` | `finishReason: { unified: 'stop' }` |
| `task_error` | `finish` | `finishReason: { unified: 'error' }` |
| `breakpoint_tool_call` | `finish` | `finishReason: { unified: 'tool-calls' }` |

## Provider Metadata

The provider exposes MAIL-specific data via `providerMetadata.mail`:

```typescript
interface MAILProviderMetadata {
  // Task tracking
  taskId: string;
  taskStatus: 'running' | 'completed' | 'error' | 'paused';

  // Agent visibility
  currentAgent: string | null;
  agentTrace: Array<{
    agent: string;
    timestamp: string;
    event: string;
  }>;

  // Full event history (optional, can be large)
  events?: MAILEvent[];

  // For task continuation
  resumeToken?: string;
}
```

## File Structure

```
packages/mail-ai-sdk-provider/
├── src/
│   ├── index.ts                    # Public exports
│   ├── mail-provider.ts            # Provider factory
│   ├── mail-language-model.ts      # LanguageModelV3 implementation
│   ├── mail-stream-transformer.ts  # SSE → StreamPart transformer
│   ├── convert-to-mail-message.ts  # Prompt → MAIL message
│   └── types.ts                    # TypeScript types
├── package.json
└── tsconfig.json
```

---

## Implementation

### 1. Types (`types.ts`)

```typescript
import type { LanguageModelV3FinishReason } from '@ai-sdk/provider';

export interface MAILProviderSettings {
  /**
   * Base URL for MAIL server
   * @default 'http://localhost:8000'
   */
  baseUrl?: string;

  /**
   * Auth token for MAIL API
   */
  authToken?: string;

  /**
   * Custom headers
   */
  headers?: Record<string, string>;

  /**
   * Whether to include agent-to-agent messages in stream
   * @default false
   */
  includeAgentChatter?: boolean;
}

export interface MAILModelSettings {
  /**
   * Swarm name (if server hosts multiple)
   */
  swarm?: string;

  /**
   * Override entrypoint agent
   */
  entrypoint?: string;

  /**
   * Existing task ID for continuation
   */
  taskId?: string;

  /**
   * Resume from specific point
   */
  resumeFrom?: 'user_response' | 'breakpoint_tool_call';
}

export interface MAILProviderMetadata {
  taskId: string;
  taskStatus: 'running' | 'completed' | 'error' | 'paused';
  currentAgent: string | null;
  agentTrace: Array<{
    agent: string;
    timestamp: string;
    event: string;
  }>;
  events?: MAILEvent[];
  resumeToken?: string;
  error?: string;
}

export interface MAILEvent {
  event: string;
  data: {
    timestamp: string;
    description: string;
    task_id: string;
    extra_data?: Record<string, unknown>;
  };
}

// V3 usage structure
export interface MAILUsage {
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
}

// V3 finish reason structure
export interface MAILFinishReason {
  unified: 'stop' | 'length' | 'content-filter' | 'tool-calls' | 'error' | 'other';
  raw?: string;
}
```

### 2. Provider Entry Point (`mail-provider.ts`)

```typescript
import { withoutTrailingSlash } from '@ai-sdk/provider-utils';
import { MAILLanguageModel } from './mail-language-model';
import type { MAILProviderSettings, MAILModelSettings } from './types';

export interface MAILProvider {
  (modelId: string, settings?: MAILModelSettings): MAILLanguageModel;
  languageModel(modelId: string, settings?: MAILModelSettings): MAILLanguageModel;
}

export function createMAIL(options: MAILProviderSettings = {}): MAILProvider {
  const baseUrl = withoutTrailingSlash(options.baseUrl) ?? 'http://localhost:8000';

  const createModel = (modelId: string, settings: MAILModelSettings = {}) => {
    return new MAILLanguageModel(modelId, settings, {
      provider: 'mail',
      baseUrl,
      headers: () => ({
        'Content-Type': 'application/json',
        ...(options.authToken && { Authorization: `Bearer ${options.authToken}` }),
        ...options.headers,
      }),
      includeAgentChatter: options.includeAgentChatter ?? false,
    });
  };

  const provider = function (modelId: string, settings?: MAILModelSettings) {
    return createModel(modelId, settings);
  } as MAILProvider;

  provider.languageModel = createModel;

  return provider;
}

// Default instance
export const mail = createMAIL();
```

### 3. Language Model (`mail-language-model.ts`)

```typescript
import type {
  LanguageModelV3,
  LanguageModelV3CallOptions,
  LanguageModelV3StreamPart,
} from '@ai-sdk/provider';
import { convertToMAILMessage } from './convert-to-mail-message';
import { createMAILStreamTransformer } from './mail-stream-transformer';
import type { MAILModelSettings, MAILUsage, MAILFinishReason } from './types';

interface MAILConfig {
  provider: string;
  baseUrl: string;
  headers: () => Record<string, string>;
  includeAgentChatter: boolean;
}

export class MAILLanguageModel implements LanguageModelV3 {
  // V3 spec requires lowercase 'v3'
  readonly specificationVersion = 'v3' as const;
  readonly provider: string;
  readonly modelId: string;

  private readonly settings: MAILModelSettings;
  private readonly config: MAILConfig;

  constructor(
    modelId: string,
    settings: MAILModelSettings,
    config: MAILConfig
  ) {
    this.modelId = modelId;
    this.settings = settings;
    this.config = config;
    this.provider = config.provider;
  }

  /**
   * Non-streaming generation
   */
  async doGenerate(options: LanguageModelV3CallOptions): Promise<{
    content: Array<{ type: 'text'; text: string }>;
    finishReason: MAILFinishReason;
    usage: MAILUsage;
    warnings: Array<{ message: string }>;
    providerMetadata?: { mail: Record<string, unknown> };
  }> {
    const { body, warnings } = this.buildRequest(options, false);

    const response = await fetch(`${this.config.baseUrl}/ui/message`, {
      method: 'POST',
      headers: this.config.headers(),
      body: JSON.stringify(body),
      signal: options.abortSignal,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`MAIL request failed: ${response.status} ${errorText}`);
    }

    const result = await response.json();

    // Extract final response
    const content: Array<{ type: 'text'; text: string }> = [];
    if (result.response) {
      content.push({ type: 'text', text: result.response });
    }

    const finishReason: MAILFinishReason = {
      unified: result.completed ? 'stop' : 'error',
      raw: result.completed ? 'task_complete' : 'task_error',
    };

    // MAIL doesn't track tokens currently
    const usage: MAILUsage = {
      inputTokens: { total: 0, noCache: 0 },
      outputTokens: { total: 0, text: 0 },
    };

    return {
      content,
      finishReason,
      usage,
      warnings,
      providerMetadata: {
        mail: {
          taskId: result.task_id,
          taskStatus: result.completed ? 'completed' : 'error',
          events: result.events,
        },
      },
    };
  }

  /**
   * Streaming generation - the main interface for MAIL
   */
  async doStream(options: LanguageModelV3CallOptions): Promise<{
    stream: ReadableStream<LanguageModelV3StreamPart>;
    warnings: Array<{ message: string }>;
  }> {
    const { body, warnings } = this.buildRequest(options, true);

    const response = await fetch(`${this.config.baseUrl}/ui/message`, {
      method: 'POST',
      headers: this.config.headers(),
      body: JSON.stringify(body),
      signal: options.abortSignal,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`MAIL request failed: ${response.status} ${errorText}`);
    }

    if (!response.body) {
      throw new Error('No response body');
    }

    // Transform MAIL SSE stream to AI SDK stream parts
    const stream = response.body
      .pipeThrough(new TextDecoderStream())
      .pipeThrough(createSSEParser())
      .pipeThrough(
        createMAILStreamTransformer({
          includeAgentChatter: this.config.includeAgentChatter,
          taskId: body.task_id as string,
        })
      );

    return { stream, warnings };
  }

  /**
   * Build MAIL request body from AI SDK options
   */
  private buildRequest(
    options: LanguageModelV3CallOptions,
    stream: boolean
  ): { body: Record<string, unknown>; warnings: Array<{ message: string }> } {
    const warnings: Array<{ message: string }> = [];

    // Convert AI SDK prompt to MAIL message body
    const { messageBody, toolResults } = convertToMAILMessage(options.prompt);

    // Generate or reuse task ID
    const taskId = this.settings.taskId || crypto.randomUUID();

    const body: Record<string, unknown> = {
      body: messageBody,
      subject: 'AI SDK Request',
      stream,
      task_id: taskId,
      entrypoint: this.settings.entrypoint,
    };

    // Handle task continuation
    if (this.settings.taskId && this.settings.resumeFrom) {
      body.resume_from = this.settings.resumeFrom;
    }

    // Handle tool results (continuing after tool-calls finish reason)
    if (toolResults.length > 0) {
      body.resume_from = 'breakpoint_tool_call';
      body.kwargs = { tool_results: toolResults };
    }

    // Warn about unsupported features
    if (options.temperature !== undefined) {
      warnings.push({
        message: 'temperature is controlled by individual agents in the swarm',
      });
    }

    if (options.maxOutputTokens !== undefined) {
      warnings.push({
        message: 'maxOutputTokens is controlled by individual agents in the swarm',
      });
    }

    if (options.tools && options.tools.length > 0) {
      warnings.push({
        message: 'Dynamic tools not yet supported. Define actions in swarms.json.',
      });
    }

    return { body, warnings };
  }
}

/**
 * Parse SSE stream into events
 */
function createSSEParser(): TransformStream<string, { event: string; data: unknown }> {
  let buffer = '';

  return new TransformStream({
    transform(chunk, controller) {
      buffer += chunk;
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      let currentEvent = 'message';
      let currentData = '';

      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          currentData = line.slice(5).trim();
        } else if (line === '' && currentData) {
          // Empty line = end of event
          try {
            controller.enqueue({
              event: currentEvent,
              data: JSON.parse(currentData),
            });
          } catch {
            // Skip unparseable events
          }
          currentEvent = 'message';
          currentData = '';
        }
      }
    },

    flush(controller) {
      // Handle any remaining data
      if (buffer.trim()) {
        try {
          const data = JSON.parse(buffer);
          controller.enqueue({ event: 'message', data });
        } catch {
          // Ignore
        }
      }
    },
  });
}
```

### 4. Stream Transformer (`mail-stream-transformer.ts`)

```typescript
import type { LanguageModelV3StreamPart } from '@ai-sdk/provider';
import type { MAILUsage, MAILFinishReason, MAILProviderMetadata } from './types';

interface MAILEventData {
  timestamp: string;
  description: string;
  task_id: string;
  extra_data?: {
    tool_name?: string;
    tool_args?: Record<string, unknown>;
    tool_call_id?: string;
    reasoning?: string;
    full_message?: {
      message?: { body?: string; sender?: { address: string } };
      msg_type?: string;
    };
    response?: string;
    error?: string;
  };
}

interface TransformerOptions {
  includeAgentChatter: boolean;
  taskId: string;
}

export function createMAILStreamTransformer(
  options: TransformerOptions
): TransformStream<{ event: string; data: unknown }, LanguageModelV3StreamPart> {
  let currentAgent: string | null = null;
  let textIdCounter = 0;
  let reasoningIdCounter = 0;
  let activeTextId: string | null = null;
  let activeReasoningId: string | null = null;
  const agentTrace: MAILProviderMetadata['agentTrace'] = [];

  // Helper to create usage object
  const createUsage = (): MAILUsage => ({
    inputTokens: { total: 0, noCache: 0 },
    outputTokens: { total: 0, text: 0 },
  });

  return new TransformStream({
    transform(chunk, controller) {
      const { event, data } = chunk as { event: string; data: MAILEventData };

      // Skip ping events
      if (event === 'ping') return;

      // Track agent activity
      const agentMatch = data.description?.match(/^agent (\w+)/i);
      if (agentMatch) {
        currentAgent = agentMatch[1];
        agentTrace.push({
          agent: currentAgent,
          timestamp: data.timestamp,
          event,
        });
      }

      // Handle different event types
      switch (event) {
        case 'new_message': {
          const fullMessage = data.extra_data?.full_message;
          const msgType = fullMessage?.msg_type;
          const body = fullMessage?.message?.body;

          // broadcast_complete is the final response
          if (msgType === 'broadcast_complete' && body) {
            // Start new text block
            const textId = `text-${++textIdCounter}`;
            activeTextId = textId;

            controller.enqueue({ type: 'text-start', id: textId });
            controller.enqueue({ type: 'text-delta', id: textId, delta: body });
            controller.enqueue({ type: 'text-end', id: textId });

            activeTextId = null;
          }
          // Optionally include agent-to-agent messages
          else if (options.includeAgentChatter && body && msgType !== 'broadcast_complete') {
            const textId = `chatter-${++textIdCounter}`;

            controller.enqueue({ type: 'text-start', id: textId });
            controller.enqueue({
              type: 'text-delta',
              id: textId,
              delta: `[${currentAgent}]: ${body}\n`,
            });
            controller.enqueue({ type: 'text-end', id: textId });
          }
          break;
        }

        case 'tool_call':
        case 'action_call': {
          const extra = data.extra_data;
          if (extra?.tool_name) {
            // Emit reasoning if present
            if (extra.reasoning) {
              const reasoningId = `reasoning-${++reasoningIdCounter}`;

              controller.enqueue({ type: 'reasoning-start', id: reasoningId });
              controller.enqueue({
                type: 'reasoning-delta',
                id: reasoningId,
                delta: extra.reasoning,
              });
              controller.enqueue({ type: 'reasoning-end', id: reasoningId });
            }

            // Emit tool call - note: input is object, not string
            controller.enqueue({
              type: 'tool-call',
              toolCallId: extra.tool_call_id || crypto.randomUUID(),
              toolName: extra.tool_name,
              input: extra.tool_args || {},
            });
          }
          break;
        }

        case 'task_complete': {
          const response = data.extra_data?.response;

          // Emit any final response text
          if (response) {
            const textId = `text-${++textIdCounter}`;
            controller.enqueue({ type: 'text-start', id: textId });
            controller.enqueue({ type: 'text-delta', id: textId, delta: response });
            controller.enqueue({ type: 'text-end', id: textId });
          }

          // Emit finish with V3 structure
          const finishReason: MAILFinishReason = {
            unified: 'stop',
            raw: 'task_complete',
          };

          controller.enqueue({
            type: 'finish',
            finishReason,
            usage: createUsage(),
            providerMetadata: {
              mail: {
                taskId: options.taskId,
                taskStatus: 'completed',
                currentAgent,
                agentTrace,
              } satisfies Partial<MAILProviderMetadata>,
            },
          });
          break;
        }

        case 'task_error': {
          const finishReason: MAILFinishReason = {
            unified: 'error',
            raw: data.extra_data?.error || data.description,
          };

          controller.enqueue({
            type: 'finish',
            finishReason,
            usage: createUsage(),
            providerMetadata: {
              mail: {
                taskId: options.taskId,
                taskStatus: 'error',
                currentAgent,
                agentTrace,
                error: data.extra_data?.error || data.description,
              } satisfies Partial<MAILProviderMetadata>,
            },
          });
          break;
        }

        case 'breakpoint_tool_call': {
          // Task paused waiting for user input
          const finishReason: MAILFinishReason = {
            unified: 'tool-calls',
            raw: 'breakpoint_tool_call',
          };

          controller.enqueue({
            type: 'finish',
            finishReason,
            usage: createUsage(),
            providerMetadata: {
              mail: {
                taskId: options.taskId,
                taskStatus: 'paused',
                currentAgent,
                agentTrace,
                resumeToken: 'breakpoint_tool_call',
              } satisfies Partial<MAILProviderMetadata>,
            },
          });
          break;
        }
      }
    },
  });
}
```

### 5. Message Conversion (`convert-to-mail-message.ts`)

```typescript
import type { LanguageModelV3Prompt } from '@ai-sdk/provider';

interface ConversionResult {
  messageBody: string;
  toolResults: Array<{
    toolCallId: string;
    toolName: string;
    result: unknown;
  }>;
}

/**
 * Convert AI SDK prompt to MAIL message body
 *
 * MAIL expects a simple text message body, not a complex message array.
 * We extract the latest user message and any tool results.
 */
export function convertToMAILMessage(prompt: LanguageModelV3Prompt): ConversionResult {
  const toolResults: ConversionResult['toolResults'] = [];
  let messageBody = '';
  let systemContext = '';

  for (const message of prompt) {
    switch (message.role) {
      case 'system':
        // Collect system messages as context
        if (typeof message.content === 'string') {
          systemContext += message.content + '\n';
        } else if (Array.isArray(message.content)) {
          for (const part of message.content) {
            if (part.type === 'text') {
              systemContext += part.text + '\n';
            }
          }
        }
        break;

      case 'user':
        // Extract text from user message (take the last one)
        if (Array.isArray(message.content)) {
          for (const part of message.content) {
            if (part.type === 'text') {
              messageBody = part.text;
            }
            // Note: MAIL doesn't support images/files yet
            // Could add warning or convert to description
          }
        }
        break;

      case 'assistant':
        // Assistant messages are part of history
        // MAIL handles this via task continuation
        break;

      case 'tool':
        // Tool results need to be passed back to MAIL
        if (Array.isArray(message.content)) {
          for (const part of message.content) {
            if (part.type === 'tool-result') {
              toolResults.push({
                toolCallId: part.toolCallId,
                toolName: part.toolName,
                result: part.output,  // Note: V3 uses 'output' not 'result'
              });
            }
          }
        }
        break;
    }
  }

  // Prepend system context if present
  if (systemContext.trim()) {
    messageBody = `[System Context]\n${systemContext.trim()}\n\n[User Message]\n${messageBody}`;
  }

  return { messageBody, toolResults };
}
```

### 6. Public Exports (`index.ts`)

```typescript
export { createMAIL, mail } from './mail-provider';
export type {
  MAILProvider,
  MAILProviderSettings,
  MAILModelSettings,
} from './mail-provider';
export { MAILLanguageModel } from './mail-language-model';
export type { MAILProviderMetadata, MAILEvent } from './types';
```

---

## Usage Examples

### Basic Usage

```typescript
import { streamText } from 'ai';
import { mail } from '@mail/ai-sdk-provider';

const result = await streamText({
  model: mail('research-swarm'),
  prompt: 'Research the latest developments in quantum computing',
});

for await (const chunk of result.textStream) {
  process.stdout.write(chunk);
}

// Access MAIL-specific metadata
const metadata = await result.providerMetadata;
console.log('Task ID:', metadata?.mail?.taskId);
console.log('Agent trace:', metadata?.mail?.agentTrace);
```

### With Custom Configuration

```typescript
import { createMAIL } from '@mail/ai-sdk-provider';

const mail = createMAIL({
  baseUrl: 'https://mail.example.com',
  authToken: process.env.MAIL_API_KEY,
  includeAgentChatter: true, // See agent-to-agent messages
});

const result = await streamText({
  model: mail('customer-support', {
    entrypoint: 'triage-agent',
  }),
  prompt: 'I need help with my order #12345',
});
```

### Task Continuation

```typescript
import { streamText } from 'ai';
import { mail } from '@mail/ai-sdk-provider';

// Initial request
const response1 = await streamText({
  model: mail('research-swarm'),
  prompt: 'Research quantum computing',
});

const taskId = (await response1.providerMetadata)?.mail?.taskId;

// Continue the same task
const response2 = await streamText({
  model: mail('research-swarm', {
    taskId,
    resumeFrom: 'user_response',
  }),
  prompt: 'Now compare it to classical computing',
});
```

### Next.js Route Handler

```typescript
// app/api/chat/route.ts
import { convertToModelMessages, streamText, UIMessage } from 'ai';
import { mail } from '@mail/ai-sdk-provider';

export const maxDuration = 60; // MAIL tasks can take longer

export async function POST(req: Request) {
  const { messages, taskId }: { messages: UIMessage[]; taskId?: string } =
    await req.json();

  const result = streamText({
    model: mail('assistant-swarm', {
      taskId,
      resumeFrom: taskId ? 'user_response' : undefined,
    }),
    messages: await convertToModelMessages(messages),
  });

  return result.toUIMessageStreamResponse();
}
```

### With AI Elements Components

```typescript
'use client';

import { useChat } from '@ai-sdk/react';
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from '@/components/ai-elements/reasoning';

export default function Chat() {
  const { messages, sendMessage, input, setInput, data } = useChat({
    api: '/api/chat',
  });

  return (
    <div>
      {messages.map((m) => (
        <div key={m.id}>
          {/* Show reasoning if present */}
          {m.reasoning && (
            <Reasoning>
              <ReasoningTrigger />
              <ReasoningContent>{m.reasoning}</ReasoningContent>
            </Reasoning>
          )}
          {m.parts.map((part, i) =>
            part.type === 'text' ? <p key={i}>{part.text}</p> : null
          )}
        </div>
      ))}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage({ text: input });
          setInput('');
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} />
      </form>
    </div>
  );
}
```

---

## Package.json

```json
{
  "name": "@mail/ai-sdk-provider",
  "version": "0.1.0",
  "description": "AI SDK provider for MAIL multi-agent runtime",
  "type": "module",
  "main": "dist/index.js",
  "module": "dist/index.mjs",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.mjs",
      "require": "./dist/index.js",
      "types": "./dist/index.d.ts"
    }
  },
  "files": ["dist"],
  "peerDependencies": {
    "@ai-sdk/provider": "^1.0.0"
  },
  "dependencies": {
    "@ai-sdk/provider-utils": "^2.0.0"
  },
  "devDependencies": {
    "@ai-sdk/provider": "^1.0.0",
    "typescript": "^5.0.0",
    "tsup": "^8.0.0"
  },
  "scripts": {
    "build": "tsup src/index.ts --format cjs,esm --dts",
    "dev": "tsup src/index.ts --format cjs,esm --dts --watch",
    "typecheck": "tsc --noEmit"
  }
}
```

---

## Key Differences from v1

| Aspect | v1 (Original) | v2 (Corrected) |
|--------|---------------|----------------|
| `specificationVersion` | `'V3' as const` | `'v3' as const` |
| Text streaming | Single `{ type: 'text' }` | `text-start` → `text-delta` → `text-end` |
| Text content | `text: string` | `delta: string` |
| Stream start | `{ type: 'stream-start' }` | Removed (not a valid type) |
| Response metadata | `{ type: 'response-metadata' }` | Removed (not a valid type) |
| Finish reason | `'stop'` (string) | `{ unified: 'stop', raw: '...' }` |
| Usage | `{ inputTokens?: number }` | `{ inputTokens: { total, noCache, ... } }` |
| Tool call args | `args: string` (JSON) | `input: object` |
| Reasoning | `{ type: 'reasoning' }` | `reasoning-start` → `reasoning-delta` → `reasoning-end` |
| Warnings | `{ type, message }` | `{ message }` |

---

## Future Enhancements

### 1. Dynamic Tool Registration

```typescript
const response = await streamText({
  model: mail('research-swarm'),
  tools: {
    searchWeb: {
      description: 'Search the web',
      parameters: z.object({ query: z.string() }),
      execute: async ({ query }) => {
        // Register as MAIL action at runtime
      },
    },
  },
});
```

### 2. Streaming Agent Events

```typescript
// Access agent events as they happen
for await (const event of result.experimental_providerStream) {
  if (event.type === 'mail-agent-event') {
    console.log(`[${event.agent}] ${event.description}`);
  }
}
```

### 3. Multi-Swarm Orchestration

```typescript
const result = await streamText({
  model: mail('orchestrator', {
    childSwarms: ['research', 'writing', 'review'],
  }),
  prompt: 'Write a comprehensive report on AI safety',
});
```
