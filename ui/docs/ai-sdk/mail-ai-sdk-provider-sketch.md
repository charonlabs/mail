# MAIL AI SDK Provider - Implementation Sketch

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
│    model: mail({ baseUrl, swarm: 'research-team' }),        │
│    prompt: 'Research quantum computing',                    │
│    tools: { ... }  // Optional additional tools             │
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
│  │ doGenerate()   │───▶│  MAIL SSE → AI SDK StreamParts  │ │
│  │ doStream()     │    │                                 │ │
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
| (connection open) | `stream-start` | Include warnings if any |
| `new_message` (broadcast_complete) | `text` | Final response text |
| `new_message` (agent→agent) | `text` + providerMetadata | Show agent chatter optionally |
| `tool_call` | `tool-call` | Agent invoking MAIL tool |
| `action_call` | `tool-call` | Agent invoking custom action |
| `action_complete` | (update providerMetadata) | Action result |
| `task_complete` | `finish` | finishReason: 'stop' |
| `task_error` | `error` or `finish` | finishReason: 'error' |
| `breakpoint_tool_call` | `finish` | finishReason: 'tool-calls' (needs user input) |

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

### 1. Provider Entry Point (`mail-provider.ts`)

```typescript
import { ProviderV3 } from '@ai-sdk/provider';
import { withoutTrailingSlash } from '@ai-sdk/provider-utils';
import { MAILLanguageModel } from './mail-language-model';

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

export interface MAILProvider extends ProviderV3 {
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
  };

  provider.languageModel = createModel;

  // MAIL doesn't support embeddings or images directly
  provider.embeddingModel = () => {
    throw new Error('MAIL provider does not support embedding models');
  };
  provider.imageModel = () => {
    throw new Error('MAIL provider does not support image models');
  };

  return provider as MAILProvider;
}

// Default instance
export const mail = createMAIL();
```

### 2. Language Model (`mail-language-model.ts`)

```typescript
import {
  LanguageModelV3,
  LanguageModelV3CallOptions,
  LanguageModelV3Content,
  LanguageModelV3StreamPart,
} from '@ai-sdk/provider';
import { convertToMAILMessage } from './convert-to-mail-message';
import { createMAILStreamTransformer } from './mail-stream-transformer';
import { MAILModelSettings } from './mail-provider';

interface MAILConfig {
  provider: string;
  baseUrl: string;
  headers: () => Record<string, string>;
  includeAgentChatter: boolean;
}

export class MAILLanguageModel implements LanguageModelV3 {
  readonly specificationVersion = 'V3' as const;
  readonly provider: string;
  readonly modelId: string;

  private readonly settings: MAILModelSettings;
  private readonly config: MAILConfig;

  constructor(
    modelId: string,
    settings: MAILModelSettings,
    config: MAILConfig
  ) {
    this.modelId = modelId; // Could be swarm name or 'default'
    this.settings = settings;
    this.config = config;
    this.provider = config.provider;
  }

  // MAIL doesn't need URL support for files (not multimodal in this sense)
  get supportedUrls(): Record<string, RegExp[]> {
    return {};
  }

  /**
   * Non-streaming generation
   */
  async doGenerate(options: LanguageModelV3CallOptions): Promise<{
    content: LanguageModelV3Content[];
    finishReason: 'stop' | 'length' | 'content-filter' | 'tool-calls' | 'error' | 'other';
    usage: { inputTokens?: number; outputTokens?: number; totalTokens?: number };
    request: { body: unknown };
    response: { body: unknown };
    warnings: Array<{ type: string; message: string }>;
    providerMetadata?: Record<string, unknown>;
  }> {
    const { body, warnings } = this.buildRequest(options, false);

    const response = await fetch(`${this.config.baseUrl}/ui/message`, {
      method: 'POST',
      headers: this.config.headers(),
      body: JSON.stringify(body),
      signal: options.abortSignal,
    });

    if (!response.ok) {
      throw new Error(`MAIL request failed: ${response.statusText}`);
    }

    const result = await response.json();

    // Extract final response from task_complete event or response field
    const content: LanguageModelV3Content[] = [];

    if (result.response) {
      content.push({ type: 'text', text: result.response });
    }

    // Extract any tool calls from events
    if (result.events) {
      for (const event of result.events) {
        if (event.event === 'action_call' && event.extra_data) {
          content.push({
            type: 'tool-call',
            toolCallType: 'function',
            toolCallId: event.extra_data.tool_call_id || event.id,
            toolName: event.extra_data.tool_name,
            args: JSON.stringify(event.extra_data.tool_args || {}),
          });
        }
      }
    }

    return {
      content,
      finishReason: result.completed ? 'stop' : 'error',
      usage: {
        inputTokens: undefined, // MAIL doesn't track tokens currently
        outputTokens: undefined,
        totalTokens: undefined,
      },
      request: { body },
      response: { body: result },
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
    warnings: Array<{ type: string; message: string }>;
    request: { body: unknown };
  }> {
    const { body, warnings } = this.buildRequest(options, true);

    const response = await fetch(`${this.config.baseUrl}/ui/message`, {
      method: 'POST',
      headers: this.config.headers(),
      body: JSON.stringify(body),
      signal: options.abortSignal,
    });

    if (!response.ok) {
      throw new Error(`MAIL request failed: ${response.statusText}`);
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
          warnings,
          includeAgentChatter: this.config.includeAgentChatter,
          taskId: body.task_id,
        })
      );

    return {
      stream,
      warnings,
      request: { body },
    };
  }

  /**
   * Build MAIL request body from AI SDK options
   */
  private buildRequest(
    options: LanguageModelV3CallOptions,
    stream: boolean
  ): { body: Record<string, unknown>; warnings: Array<{ type: string; message: string }> } {
    const warnings: Array<{ type: string; message: string }> = [];

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
        type: 'unsupported-setting',
        message: 'temperature is controlled by individual agents in the swarm',
      });
    }

    if (options.maxOutputTokens !== undefined) {
      warnings.push({
        type: 'unsupported-setting',
        message: 'maxOutputTokens is controlled by individual agents in the swarm',
      });
    }

    // Tools passed to AI SDK could be mapped to MAIL actions
    // but this requires runtime registration - warn for now
    if (options.tools && options.tools.length > 0) {
      warnings.push({
        type: 'unsupported-setting',
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
      const events = buffer.split('\r\n\r\n');
      buffer = events.pop() || '';

      for (const eventBlock of events) {
        if (!eventBlock.trim()) continue;

        let eventType = 'message';
        let eventData = '';

        for (const line of eventBlock.split('\r\n')) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            eventData = line.slice(5).trim();
          }
        }

        if (eventData) {
          try {
            controller.enqueue({
              event: eventType,
              data: JSON.parse(eventData),
            });
          } catch {
            // Skip unparseable events
          }
        }
      }
    },
  });
}
```

### 3. Stream Transformer (`mail-stream-transformer.ts`)

```typescript
import { LanguageModelV3StreamPart } from '@ai-sdk/provider';

interface MAILEvent {
  event: string;
  data: {
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
  };
}

interface TransformerOptions {
  warnings: Array<{ type: string; message: string }>;
  includeAgentChatter: boolean;
  taskId: string;
}

export function createMAILStreamTransformer(
  options: TransformerOptions
): TransformStream<{ event: string; data: unknown }, LanguageModelV3StreamPart> {
  let isFirstChunk = true;
  let currentAgent: string | null = null;
  const agentTrace: Array<{ agent: string; timestamp: string; event: string }> = [];

  return new TransformStream({
    transform(chunk, controller) {
      const { event, data } = chunk as { event: string; data: MAILEvent['data'] };

      // Send stream-start on first chunk
      if (isFirstChunk) {
        controller.enqueue({
          type: 'stream-start',
          warnings: options.warnings,
        });
        isFirstChunk = false;
      }

      // Skip ping events
      if (event === 'ping') return;

      // Track agent activity
      const agentMatch = data.description?.match(/^agent (\w+)/);
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
            controller.enqueue({
              type: 'text',
              text: body,
              providerMetadata: {
                mail: { currentAgent, taskId: options.taskId },
              },
            });
          }
          // Optionally include agent-to-agent messages
          else if (options.includeAgentChatter && body) {
            controller.enqueue({
              type: 'text',
              text: `[${currentAgent}]: ${body}\n`,
              providerMetadata: {
                mail: { currentAgent, isAgentChatter: true },
              },
            });
          }
          break;
        }

        case 'tool_call':
        case 'action_call': {
          const extra = data.extra_data;
          if (extra?.tool_name) {
            // Emit reasoning if present
            if (extra.reasoning) {
              controller.enqueue({
                type: 'reasoning',
                text: extra.reasoning,
                providerMetadata: {
                  mail: { currentAgent },
                },
              });
            }

            controller.enqueue({
              type: 'tool-call',
              toolCallType: 'function',
              toolCallId: extra.tool_call_id || crypto.randomUUID(),
              toolName: extra.tool_name,
              args: JSON.stringify(extra.tool_args || {}),
            });
          }
          break;
        }

        case 'task_complete': {
          const response = data.extra_data?.response;
          if (response) {
            controller.enqueue({
              type: 'text',
              text: response,
            });
          }

          controller.enqueue({
            type: 'response-metadata',
            modelId: 'mail-swarm',
            headers: {},
          });

          controller.enqueue({
            type: 'finish',
            finishReason: 'stop',
            usage: {
              inputTokens: undefined,
              outputTokens: undefined,
              totalTokens: undefined,
            },
            providerMetadata: {
              mail: {
                taskId: options.taskId,
                taskStatus: 'completed',
                agentTrace,
              },
            },
          });
          break;
        }

        case 'task_error': {
          controller.enqueue({
            type: 'finish',
            finishReason: 'error',
            usage: {},
            providerMetadata: {
              mail: {
                taskId: options.taskId,
                taskStatus: 'error',
                error: data.extra_data?.error || data.description,
                agentTrace,
              },
            },
          });
          break;
        }

        case 'breakpoint_tool_call': {
          // Task paused waiting for user input
          controller.enqueue({
            type: 'finish',
            finishReason: 'tool-calls',
            usage: {},
            providerMetadata: {
              mail: {
                taskId: options.taskId,
                taskStatus: 'paused',
                resumeToken: 'breakpoint_tool_call',
                agentTrace,
              },
            },
          });
          break;
        }
      }
    },
  });
}
```

### 4. Message Conversion (`convert-to-mail-message.ts`)

```typescript
import { LanguageModelV3Prompt } from '@ai-sdk/provider';

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

  for (const message of prompt) {
    switch (message.role) {
      case 'system':
        // System messages could be prepended or sent as context
        // For now, include in the message body
        if (typeof message.content === 'string') {
          messageBody = `[System]: ${message.content}\n\n${messageBody}`;
        }
        break;

      case 'user':
        // Extract text from user message
        for (const part of message.content) {
          if (part.type === 'text') {
            messageBody = part.text;
          }
          // File parts would need special handling
          // MAIL doesn't natively support file uploads yet
        }
        break;

      case 'assistant':
        // Assistant messages are part of history
        // MAIL handles this via task continuation
        break;

      case 'tool':
        // Tool results need to be passed back to MAIL
        for (const part of message.content) {
          if (part.type === 'tool-result') {
            toolResults.push({
              toolCallId: part.toolCallId,
              toolName: part.toolName,
              result: part.result,
            });
          }
        }
        break;
    }
  }

  return { messageBody, toolResults };
}
```

### 5. Public Exports (`index.ts`)

```typescript
export { createMAIL, mail } from './mail-provider';
export type {
  MAILProvider,
  MAILProviderSettings,
  MAILModelSettings,
} from './mail-provider';
export { MAILLanguageModel } from './mail-language-model';
```

---

## Usage Examples

### Basic Usage

```typescript
import { streamText } from 'ai';
import { mail } from '@mail/ai-sdk-provider';

const response = await streamText({
  model: mail('research-swarm'),
  prompt: 'Research the latest developments in quantum computing',
});

for await (const chunk of response.textStream) {
  process.stdout.write(chunk);
}

// Access MAIL-specific metadata
const metadata = await response.providerMetadata;
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

const response = await streamText({
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

### With AI Elements Components

```typescript
import { useChat } from 'ai/react';
import { mail } from '@mail/ai-sdk-provider';
import { Reasoning, ReasoningTrigger, ReasoningContent } from '@/components/ai-elements/reasoning';

function ChatWithMAIL() {
  const { messages, input, handleInputChange, handleSubmit, data } = useChat({
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
          <p>{m.content}</p>
        </div>
      ))}
      <form onSubmit={handleSubmit}>
        <input value={input} onChange={handleInputChange} />
      </form>
    </div>
  );
}
```

---

## Future Enhancements

### 1. Dynamic Tool Registration

Currently tools must be defined in `swarms.json`. Future enhancement:

```typescript
const response = await streamText({
  model: mail('research-swarm'),
  prompt: 'Research and summarize',
  tools: {
    searchWeb: {
      description: 'Search the web',
      parameters: z.object({ query: z.string() }),
      execute: async ({ query }) => {
        // This would register as a MAIL action at runtime
      },
    },
  },
});
```

### 2. Agent Selection

```typescript
// Target specific agent directly
const response = await streamText({
  model: mail('swarm', {
    entrypoint: 'researcher',
    bypassSupervisor: true
  }),
  prompt: 'Search for papers on transformers',
});
```

### 3. Streaming Agent Events

Expose full agent visibility as a separate stream:

```typescript
const response = await streamText({
  model: mail('swarm'),
  prompt: 'Research this topic',
});

// Main text stream
for await (const chunk of response.textStream) {
  console.log(chunk);
}

// Separate agent event stream (via experimental API)
for await (const event of response.experimental_providerStream) {
  if (event.type === 'mail-agent-event') {
    console.log(`[${event.agent}] ${event.description}`);
  }
}
```

---

## Package.json

```json
{
  "name": "@mail/ai-sdk-provider",
  "version": "0.1.0",
  "description": "AI SDK provider for MAIL multi-agent runtime",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.mjs",
      "require": "./dist/index.js",
      "types": "./dist/index.d.ts"
    }
  },
  "peerDependencies": {
    "@ai-sdk/provider": "^1.0.0"
  },
  "dependencies": {
    "@ai-sdk/provider-utils": "^2.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "tsup": "^8.0.0"
  },
  "scripts": {
    "build": "tsup src/index.ts --format cjs,esm --dts",
    "dev": "tsup src/index.ts --format cjs,esm --dts --watch"
  }
}
```
