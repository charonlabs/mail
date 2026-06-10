# Chat-First UI Development

This document tracks the development of a new chat-first interface for MAIL, built using the AI Elements component library.

## Overview

The goal is to create a clean, ChatGPT-style chat interface that surfaces agent activity (tool calls, reasoning) inline within the conversation. This is an alternative to the existing dashboard view which shows a graph + panels layout.

## What We've Built

### `/chat` Route (Completed)

**File:** `app/chat/page.tsx`

A centered chat interface with:
- **Header** - MAIL Chat branding with connection status indicator
- **Conversation area** - Auto-scrolling message list using `Conversation` component from AI Elements
- **Message display** - User and assistant messages with markdown rendering via `MessageResponse`
- **Input area** - Rich input using `PromptInput` with Enter to submit, Shift+Enter for newlines
- **Copy action** - Copy button on assistant messages
- **Cancel button** - Stop button (red square) appears during processing

**Components used:**
- `Conversation`, `ConversationContent`, `ConversationScrollButton`
- `Message`, `MessageContent`, `MessageResponse`, `MessageActions`, `MessageAction`
- `PromptInput`, `PromptInputTextarea`, `PromptInputFooter`, `PromptInputSubmit`
- `Loader`

**Data flow:**
- Uses existing `useSSE` hook for sending messages
- Uses `useAppStore` for isProcessing, connectionStatus
- Uses `useChatTimeline` hook to merge messages and tool_call events
- Timeline sorted by timestamp, interleaving messages and tool calls

### Inline Tool Calls (Completed)

**Files:**
- `hooks/useChatTimeline.ts` - Merges messages + events into unified timeline
- `app/chat/ChatToolCall.tsx` - Renders tool calls using AI Elements Tool component

**Features:**
- Tool calls appear inline, sorted by timestamp with messages
- Running tools show pulsing "Running" badge
- Completed tools show green "Completed" badge
- Reasoning text appears in italics above each tool card
- Filters to supervisor's tool calls only (defaults to 'supervisor')
- Timestamps displayed in 12:34 format
- Tool arguments shown as syntax-highlighted JSON

**Components used:**
- `Tool`, `ToolHeader`, `ToolContent`, `ToolInput` from AI Elements

**Data flow:**
```
Store (events, messages, currentTaskId, entrypoint)
    ↓
useChatTimeline hook
    ↓ filters + merges + sorts
TimelineItem[]
    ↓
ChatPage renders
    ↓
Message component (for messages)
ChatToolCall component (for tool_call events)
```

## Reference: Event Data Structure

```typescript
interface MAILEvent {
  id: string;
  event: EventType;
  timestamp: string;
  description: string;
  task_id: string;
  extra_data?: {
    caller?: string;           // Agent that made the call
    tool_name?: string;        // Name of tool
    tool_args?: Record<string, unknown>;  // Tool arguments
    reasoning?: string[];      // Extended thinking (array of text blocks)
    preamble?: string;         // Text before tool call
    result?: string;           // Tool result (for action_complete)
  };
}
```

## Styling

Using existing MAIL theme from `globals.css`:
- Dark metallic palette (copper, bronze, gold accents)
- Monospace fonts for code/data
- Custom scrollbars
- Existing card and border styles

## File Structure

```
ui/
├── app/
│   ├── chat/
│   │   ├── page.tsx          # Chat-first interface
│   │   └── ChatToolCall.tsx  # Tool call display component
│   └── page.tsx              # Existing dashboard
├── components/
│   ├── ai-elements/          # AI Elements library
│   │   ├── tool.tsx          # Tool display component
│   │   ├── reasoning.tsx     # Extended thinking component
│   │   ├── message.tsx       # Message components
│   │   ├── conversation.tsx  # Auto-scroll container
│   │   └── ...
│   └── chat/
│       └── ChatSidebar.tsx   # Existing sidebar (reference)
├── hooks/
│   ├── useSSE.ts             # SSE connection hook
│   ├── useChatTimeline.ts    # Timeline merging hook
│   └── useTaskHistory.ts     # Task loading
├── lib/
│   └── store.ts              # Zustand store
└── docs/
    ├── chatbot-example.md    # AI SDK example (reference)
    └── chat-first-ui.md      # This file
```

## Testing

1. Start MAIL server: `uv run mail server` or eval server: `python scripts/GEPA/start_eval_swarm_server.py`
2. Start UI: `cd ui && pnpm dev`
3. Navigate to `http://localhost:3000/chat`

## Future Enhancements

Now that basic tool calls are working, potential next steps:

1. **Tool results display** - Show action_complete events with results
2. **Error display** - Show action_error, agent_error events inline
3. **Reasoning component** - Use AI Elements Reasoning component (collapsed by default)
4. **Suggestions** - Follow-up prompt chips
5. **Confirmation** - Breakpoint tool approval UI
6. **Task history** - Sidebar or dropdown for past conversations
7. **Multi-agent view** - Expand to show which agents are active in multi-agent swarms
8. **Proper connection flow** - Fetch agents on mount to get real entrypoint

---

*Last updated: January 2026*
