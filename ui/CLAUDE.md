# MAIL Swarm Viewer UI - Development Notes

This document captures architecture decisions and technical details about the MAIL UI to help future Claude instances understand the codebase without re-exploring it each time.

## Overview

The MAIL Swarm Viewer is a Next.js dashboard for visualizing and interacting with MAIL agent swarms in real-time. It displays agent topology as a graph, streams events via SSE, and provides a chat interface to interact with the supervisor.

## Tech Stack

- **Framework**: Next.js 14+ with App Router, TypeScript
- **Graph Visualization**: React Flow (@xyflow/react)
- **State Management**: Zustand (`lib/store.ts`)
- **Styling**: Tailwind CSS with custom dark metallic theme
- **Components**: Custom components with shadcn/ui as base

## Aesthetic Direction

**Terminal/Hacker with Metallic Warmth**:
- Dark background (near-black, charcoal tones)
- Gold/bronze/copper accent palette (CSS variables: `--copper`, `--bronze`, `--gold`)
- Monospace fonts for data (`JetBrains Mono`)
- Raw terminal feel with warm metallic highlights

## Architecture

### 4-Panel Layout

1. **Chat Sidebar** (left, ~320px fixed)
   - `components/chat/ChatSidebar.tsx`
   - Multi-line textarea input
   - Message history with sent/received styling
   - Sends messages to entrypoint via `/ui/message` endpoint

2. **Agent Graph** (center)
   - `components/graph/AgentGraph.tsx` + `AgentNode.tsx`
   - React Flow with force-directed layout (d3-force)
   - Nodes show agent name + role badges
   - Edges show comm_targets connections
   - Active agents get warm glow animation

3. **Agent Detail Panel** (right, slides in as overlay)
   - `components/panels/AgentDetailPanel.tsx`
   - Triggered by clicking agent node
   - Resizable width
   - Shows agent-specific events

4. **Events Panel** (bottom, slides up as overlay)
   - `components/panels/EventsPanel.tsx`
   - All SSE events with search + filter chips
   - Expandable rows showing event details

## Key Files

```
ui/
├── app/
│   ├── layout.tsx      # Root layout with dark theme
│   ├── page.tsx        # Main dashboard page
│   └── globals.css     # CSS variables and custom theme
├── components/
│   ├── graph/
│   │   ├── AgentGraph.tsx   # React Flow container
│   │   └── AgentNode.tsx    # Custom agent node component
│   ├── chat/
│   │   ├── ChatSidebar.tsx  # Chat input and history (tabbed)
│   │   └── TaskHistoryContent.tsx  # Task history tab
│   └── panels/
│       ├── AgentDetailPanel.tsx
│       └── EventsPanel.tsx
├── hooks/
│   ├── useSSE.ts           # SSE connection and message handling
│   └── useTaskHistory.ts   # Task loading hook
├── lib/
│   ├── api.ts          # MAILClient - API interactions
│   └── store.ts        # Zustand store for app state
└── types/
    └── mail.ts         # TypeScript interfaces
```

## SSE Streaming Flow

### How Messages Flow

1. **User sends message** via ChatSidebar
2. **useSSE hook** calls `client.streamMessage()` with:
   - `body`: message content
   - `taskId`: existing task ID (for follow-ups) or new UUID
   - `entrypoint`: agent to receive message
   - `resumeFrom`: `'user_response'` for follow-up messages
3. **API client** POSTs to `/ui/message` endpoint
4. **Server** returns SSE stream via `EventSourceResponse`
5. **Events are parsed** and dispatched:
   - `task_complete` / `task_error` -> Add message to chat
   - Other events -> Add to events store

### Event Types

| Event | Description |
|-------|-------------|
| `new_message` | Message sent between agents |
| `tool_call` | Agent invoked a tool |
| `task_complete` | Task finished successfully (contains `response` field) |
| `task_complete_call` | Agent called task_complete tool (precedes task_complete) |
| `task_error` | Task failed |
| `agent_error` | Agent-level error |
| `action_call` | Custom action invoked |
| `ping` | SSE heartbeat (filtered out) |

### Event Data Structure

```typescript
interface MAILEvent {
  id: string;
  event: EventType;
  timestamp: string;
  description: string;
  task_id: string;
  extra_data?: {
    tool_name?: string;
    tool_args?: Record<string, unknown>;
    tool_call_id?: string;
    reasoning?: string;
    full_message?: MAILMessagePayload;
    caller?: string;  // Added by store from description
  };
}
```

## Backend Endpoints

### `GET /ui/agents`
Returns agent topology for graph visualization:
```json
{
  "agents": [
    {
      "name": "Supervisor",
      "comm_targets": ["Researcher"],
      "enable_entrypoint": true,
      "can_complete_tasks": true
    }
  ],
  "entrypoint": "Supervisor"
}
```

### `POST /ui/message`
Debug endpoint (no auth required when `debug=true`):
```json
{
  "body": "message content",
  "subject": "User Message",
  "entrypoint": "Supervisor",
  "task_id": "uuid",
  "stream": true,
  "resume_from": "user_response"  // For follow-up messages
}
```

Returns SSE stream with events.

## State Management (Zustand)

Key state in `lib/store.ts`:

```typescript
// Connection
serverUrl: string
connectionStatus: 'disconnected' | 'connecting' | 'connected' | 'error'

// Agents
agents: Agent[]
entrypoint: string
activeAgents: Set<string>  // Agents with recent activity
selectedAgent: string | null

// Events
events: MAILEvent[]  // Last 1000 events
eventFilters: { search: string, types: EventType[], showAll: boolean }

// Chat
messages: ChatMessage[]
currentTaskId: string | null  // Preserved for follow-up messages
isProcessing: boolean

// Task History
taskHistory: TaskSummary[]
sidebarTab: 'chat' | 'history'

// Panels
isDetailPanelOpen: boolean
isEventsPanelOpen: boolean
```

## Task Continuation (Multi-turn Conversations)

To continue a conversation after task_complete:
1. Keep `currentTaskId` (don't clear it)
2. On next message, pass same `taskId` and `resumeFrom: 'user_response'`
3. Server resumes the task from user response point

## Development

### Running the Dev Environment

Use the script at `scripts/run_ui_dev.py`:
```bash
python scripts/run_ui_dev.py
```

This starts:
- MAIL server on port 8000 with a 2-agent swarm (Supervisor + Researcher)
- Next.js dev server on port 3000
- Logs MAIL server to `mail_server.log`, pnpm to terminal

### Common Issues

1. **CORS errors**: Server has CORS middleware for localhost:3000
2. **Auth errors**: Use `/ui/message` endpoint (bypasses auth in debug mode)
3. **Events not attributed to agents**: Store extracts agent name from description via regex `^agent (\w+)`
4. **Follow-up messages fail**: Must pass `resume_from: 'user_response'` with same task_id

## Task History

The chat sidebar has two tabs: **Chat** and **History**.

### History Tab Features

- Lists all tasks from the server via `GET /ui/tasks`
- Shows task status badges (Done/Running/Paused)
- Displays AI-generated titles (via Haiku) or fallback `Task {id}...`
- Click a completed task to load it into chat

### Title Generation

Titles are generated on-demand via `GET /ui/task-summary/{task_id}`:

1. Frontend fetches task list, fires parallel summary requests for tasks with `title === null`
2. Backend extracts user/assistant messages from task events
3. Calls `summarize_task()` which creates a fresh Haiku swarm per request
4. Returns title (cached on task) or failure slug (`<title failed>`, `<no messages>`)

**Key files:**
- `src/mail/summarizer.py` - TaskSummarizer using breakpoint pattern
- `ui/components/chat/TaskHistoryContent.tsx` - History tab UI
- `ui/hooks/useTaskHistory.ts` - Task loading hook

### Loading Historical Tasks

`loadTaskIntoChat()` in the store:
- Extracts chat messages from `new_message` events (user sender or `broadcast_complete`)
- Deduplicates by message ID
- Sets `currentTaskId` for follow-up messages
- Cancels any active SSE stream via shared abort controller

## Recent Fixes (January 2026)

### Agent Detail Panel Redesign

The panel now shows the full agent trace - both inputs and outputs:

**Incoming Messages** (gold colored):
- Messages sent TO the agent from other agents or users
- Shows sender, subject, and message body
- Filtered to exclude `::task_complete::` broadcasts

**Tool Calls** (primary colored):
- Tool calls made BY the agent
- Reasoning displayed in italics above the tool call
- Tool call box with tool name header and formatted arguments
- Arguments shown with syntax highlighting (green for strings, blue for other values)

**New store hook**: `useAgentTrace(agentName)` returns events chronologically:
- `new_message` events where agent is the recipient
- `tool_call` events where agent is the caller

### Events Panel Improvements

- **new_message events**: Now show clean "Sender → Recipient" format with subject as subtitle instead of verbose XML dump
- **tool_call events**: Show "agent called tool_name" format

### Unseen Activity Tracking

Agent nodes now highlight (glow effect) only when they have **unseen activity** - events that occurred after the user last viewed that agent. Clicking on an agent node automatically marks it as "viewed", clearing the highlight.

**Implementation**:

1. **Store tracking** (`lib/store.ts`):
   - `agentLastViewed: Record<string, number>` - timestamp when each agent was last viewed
   - `markAgentViewed(name)` - manually mark an agent as viewed
   - `setSelectedAgent(name)` - auto-marks agent as viewed when selected

2. **Unseen detection** (`components/graph/AgentGraph.tsx`):
   - `agentsWithUnseenActivity` useMemo computes which agents have events newer than their last viewed timestamp
   - Checks both `caller` (for tool calls) and recipient (for messages) to detect activity
   - Node `isActive` property and edge animation tied to this set

3. **Store hooks**:
   - `useAgentHasUnseenActivity(agentName)` - check if single agent has unseen activity
   - Used for potential future UI indicators (e.g., badges, notifications)

## Evaluation Server Integration

The UI can connect to MASter's evaluation server (`scripts/GEPA/eval_server.py`) to visualize evaluation runs with judging and GEPA reflection.

### Running the Eval Server

```bash
# From MASter directory
uv run python scripts/GEPA/eval_server.py --port 8001

# Configure via CLI args:
#   --eval-set: Eval set name (default: hard_questions)
#   --q-idx: Question index (default: 0)
#   --model: Model ID for swarm agents
#   --reflector-model: Model ID for GEPA reflector
#   --pass-threshold: Score threshold for passing (default: 0.75)
```

### Connecting the UI

Change `NEXT_PUBLIC_MAIL_SERVER_URL` to point to the eval server:
```bash
NEXT_PUBLIC_MAIL_SERVER_URL=http://localhost:8001 pnpm dev
```

Or update in `.env.local`.

### Evaluation Event Types

The eval server emits these additional events:

| Event | Description |
|-------|-------------|
| `eval_start` | Evaluation beginning |
| `eval_config` | Question/example being evaluated |
| `rollout_start` | Swarm execution starting |
| `rollout_complete` | Swarm execution finished |
| `judge_start` | Judge evaluation starting |
| `judge_complete` | **Judge finished with scores and feedback** |
| `reflection_start` | GEPA reflection starting for agent |
| `reflection_complete` | **Reflection finished with proposed prompt changes** |
| `reflection_error` | Reflection failed |

### Key Data in Events

**`judge_complete.extra_data`:**
```typescript
{
  passed: boolean,
  score: number,
  threshold: number,
  feedback: string,
  judge_output: {
    score?: { total, max_total, rationale },
    choice?: { selected, selected_value, rationale },
  }
}
```

**`reflection_complete.extra_data`:**
```typescript
{
  agent: string,
  num_failure_analyses: number,
  num_changes: number,
  failure_analyses: [{ example_index, root_cause, explanation }],
  proposed_changes: string[],
  new_prompt_preview: string,
}
```

### API Endpoints

Same as MAIL server, plus:

- `POST /ui/config` - Update eval configuration:
  ```json
  {
    "eval_set": "hard_questions",
    "q_idx": 3,
    "model_id": "anthropic/claude-sonnet-4-5-20250929",
    "run_reflection": true
  }
  ```

## Eval Mode UI Feature

The UI supports an "Eval Mode" for connecting to the MASter evaluation server (`scripts/GEPA/eval_server.py`).

### Enabling Eval Mode

1. In the connection dialog, click the "Eval Mode" toggle
2. Configure evaluation settings:
   - **Eval Set**: Name of the eval set (default: `hard_questions`)
   - **Question #**: Index of the question to evaluate (default: 0)
   - **Model ID**: Model for swarm agents (default: `anthropic/claude-sonnet-4-5-20250929`)
   - **Reflector Model**: Model for GEPA reflection (default: `claude-opus-4-5-20251101`)
   - **Pass Threshold**: Score threshold for passing (default: 0.75)
   - **Run Reflection**: Whether to run GEPA reflection after judging

### Virtual Agents

When eval mode is enabled, two virtual agents appear at the bottom of the graph:

- **Judge** (orange, Scale icon): Shows `judge_start` and `judge_complete` events
- **Reflector** (teal, Sparkles icon): Shows `reflection_start`, `reflection_complete`, and `reflection_error` events

These virtual nodes:
- Have dashed borders instead of solid
- Use distinct colors (orange for Judge, teal for Reflector)
- Light up when their events are received (via `caller` attribution)
- Can be clicked to see their event trace in the detail panel

### Store State

```typescript
// Eval Mode
isEvalMode: boolean;
evalConfig: EvalConfig;

interface EvalConfig {
  evalSet: string;
  qIdx: number;
  modelId: string;
  reflectorModel: string;
  passThreshold: number;
  runReflection: boolean;
}
```

## Known Issues / TODOs

(None currently - main issues resolved)

## CSS Variables

Key theme variables in `globals.css`:
```css
--background: 0 0% 4%          /* Near black */
--foreground: 45 10% 90%       /* Warm white */
--primary: 38 80% 50%          /* Gold */
--copper: 24 85% 45%
--bronze: 32 70% 40%
--gold: 45 90% 55%
--edge-active: 38 80% 50%      /* For React Flow */
--edge-inactive: 0 0% 25%
--grid-color: 0 0% 15%
```
