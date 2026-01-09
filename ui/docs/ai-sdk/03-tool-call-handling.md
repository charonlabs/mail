# Tool Call Handling in AI SDK

Based on search of `ai-sdk-llms.txt`.

## Tool Call Representation in the Stream

**Message Types:**
- Tool calls appear as messages with `type: 'tool-call'` appended to the `messages` array
- In streaming context, there are two relevant event types:
  - **`tool-call`** - The main tool call event
  - **`text-delta`** - Text streaming (not tool-specific)
  - Tool calls are handled via `onStepFinish` callback in multi-step mode

**Key Quote from docs (line 593):**
> "on each generation, the model will decide whether it should call the tool. If it deems it should call the tool, it will extract the input and then append a new `message` to the `messages` array of type `tool-call`. The AI SDK will then run the `execute` function with the parameters provided by the `tool-call` message."

## Required Fields for Tool Calls

A tool call must have these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `toolCallId` | string | Yes | Unique identifier for the tool call |
| `toolName` | string | Yes | The name of the tool being invoked |
| `input` | object | Yes | The parsed arguments passed to the tool |
| `type` | string | Yes | Should be `'tool-call'` |

**Example structure (lines 9792-9794):**
```javascript
{
  type: 'tool-call',
  toolCallId: toolCall.toolCallId,
  toolName: toolCall.toolName,
  input: toolCall.input
}
```

## Tool Results Being Passed Back to Model

**Multi-step calls workflow (lines 9114-9115):**
1. The tool result is sent to the model
2. The model generates a response considering the tool result

**Key capability (lines 671, 9092):**
> "The AI SDK has a feature called `stopWhen` which allows stopping conditions when the model generates a tool call. If those stopping conditions haven't been hit, the AI SDK will automatically send tool call results back to the model!"

**Tool result structure (line 9802):**
```javascript
{
  type: 'tool-result',
  toolCallId: toolCall.toolCallId,
  toolName: toolCall.toolName,
  // ... result content
}
```

**Function `toModelOutput()` (line 2572):**
> "to send tool results back to the model, use the `toModelOutput()` function to convert text and image responses into a format the model can process"

## LanguageModelV3CallOptions.tools Structure

The tools parameter follows this structure:

**Tool Definition (lines 8877-8878):**
- **`inputSchema`**: A Zod schema or JSON schema that defines the input parameters (consumed by LLM and validates calls)
- **`execute`**: An optional async function called with inputs from the tool call (produces a value of type RESULT)
- **`description`**: String describing what the tool does
- **`needsApproval`**: Boolean (optional) - requires approval before execution

**Example tool definition (lines 8495-8521, 9351-9358):**
```javascript
inputSchema: z.object({
  location: z.string()
})
```

You can add `.describe("...")` to individual schema properties to give the model hints about what each property is for.

**Tool result is accessed via (line 9436):**
```javascript
execute: async (args, { toolCallId }) => {
  return {
    id: toolCallId,
    // result content
  }
}
```

## Multi-Step Execution Flow

**Step object contains (lines 7177, 9177):**
- `text` - Generated text from this step
- `toolCalls` - Array of tool calls made in this step
- `toolResults` - Array of results from tool execution
- `finishReason` - Why the generation finished
- `usage` - Token usage for the step

**Access in callback (line 9177):**
```javascript
onStepFinish({ text, toolCalls, toolResults, finishReason, usage })
```

**Accessing all tool calls across steps (lines 7209, 9162):**
```javascript
const allToolCalls = steps.flatMap(step => step.toolCalls);
const previousResults = steps.flatMap(step => step.toolResults);
```

## Message Array Structure for Tools

Messages in the conversation history are typed as:
- `role: 'user'` - User messages
- `role: 'assistant'` - Assistant responses (can include tool calls)
- `role: 'tool'` - Tool results/responses

**Example (lines 9788-9813):**
```javascript
messages: [
  {
    role: 'assistant',
    content: [{ type: 'tool-call', ... }]
  },
  {
    role: 'tool',
    content: [
      {
        type: 'tool-result',
        toolCallId: toolCall.toolCallId,
        toolName: toolCall.toolName
      }
    ]
  }
]
```

This creates an **automatic multi-step agentic loop** without manual intervention.
