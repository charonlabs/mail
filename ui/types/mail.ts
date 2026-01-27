// Agent types from MAIL server
export interface Agent {
  name: string;
  comm_targets: string[];
  enable_entrypoint: boolean;
  can_complete_tasks: boolean;
  enable_interswarm: boolean;
  isVirtual?: boolean;  // True for virtual nodes like Judge/Reflector in eval mode
}

export interface AgentsResponse {
  agents: Agent[];
  entrypoint: string;
}

// SSE Event types
export type EventType =
  | 'new_message'
  | 'tool_call'
  | 'task_complete'
  | 'task_error'
  | 'agent_error'
  | 'action_call'
  | 'action_complete'
  | 'action_error'
  | 'builtin_tool_call'
  | 'broadcast_ignored'
  | 'await_message'
  | 'help_called'
  | 'interswarm_message_sent'
  | 'interswarm_message_received'
  | 'interswarm_message_error'
  | 'breakpoint_tool_call'
  | 'breakpoint_action_complete'
  | 'run_loop_cancelled'
  | 'run_loop_error'
  | 'shutdown_requested'
  | 'task_complete_call'
  | 'task_complete_call_duplicate'
  | 'ping'
  // Evaluation server events
  | 'eval_start'
  | 'eval_config'
  | 'rollout_start'
  | 'rollout_complete'
  | 'judge_start'
  | 'judge_complete'
  | 'reflection_start'
  | 'reflection_complete'
  | 'reflection_error';

export interface MAILEvent {
  id: string;
  event: EventType;
  timestamp: string;
  description: string;
  task_id: string;
  extra_data?: {
    caller?: string;
    tool_name?: string;
    tool_args?: Record<string, unknown>;
    reasoning?: string[];
    preamble?: string;
    result?: string;
    message?: {
      sender?: string;
      recipient?: string;
      body?: string;
      subject?: string;
    };
    [key: string]: unknown;
  };
}

// Tool call display
export interface ToolCallDisplay {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: string;
  reasoning?: string[];
  preamble?: string;
  timestamp: string;
  status: 'pending' | 'complete' | 'error';
}

// Message types for chat
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  task_id?: string;
}

// API response types
export interface MessageResponse {
  response: string;
  events?: MAILEvent[];
}

// Graph node data
export interface AgentNodeData {
  name: string;
  isEntrypoint: boolean;
  canComplete: boolean;
  isInterswarm: boolean;
  isActive: boolean;
  eventCount: number;
  isVirtual?: boolean;  // True for virtual nodes like Judge/Reflector
  virtualType?: 'judge' | 'reflector';  // Type of virtual node
  isEvalMode?: boolean;  // True when in eval mode (for special effects)
  [key: string]: unknown; // Index signature for React Flow compatibility
}

// Connection status
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

// Filter state for events panel
export interface EventFilters {
  search: string;
  types: EventType[];
  showAll: boolean;
}

// Event type metadata for filtering UI
// Task history types
export interface TaskSummary {
  task_id: string;
  task_owner: string;
  is_running: boolean;
  completed: boolean;
  start_time: string;
  event_count: number;
  title: string | null;
}

export interface TaskWithEvents extends Omit<TaskSummary, 'event_count'> {
  events: Array<{
    event: string;
    data: {
      timestamp: string;
      description: string;
      task_id: string;
      extra_data?: Record<string, unknown>;
    } | string;  // string if parse failed
    id: string | null;
  }>;
}

export const EVENT_TYPE_META: Record<EventType, { label: string; color: string }> = {
  new_message: { label: 'Message', color: '#cfb53b' },
  tool_call: { label: 'Tool', color: '#cd7f32' },
  task_complete: { label: 'Complete', color: '#50c878' },
  task_error: { label: 'Error', color: '#dc143c' },
  agent_error: { label: 'Agent Err', color: '#ff6b35' },
  action_call: { label: 'Action', color: '#b87333' },
  action_complete: { label: 'Action Done', color: '#daa06d' },
  action_error: { label: 'Action Err', color: '#ff6b35' },
  builtin_tool_call: { label: 'Builtin', color: '#b87333' },
  broadcast_ignored: { label: 'Ignored', color: '#6b6560' },
  await_message: { label: 'Await', color: '#8b8b8b' },
  help_called: { label: 'Help', color: '#cfb53b' },
  interswarm_message_sent: { label: 'Interswarm Out', color: '#cd7f32' },
  interswarm_message_received: { label: 'Interswarm In', color: '#cfb53b' },
  interswarm_message_error: { label: 'Interswarm Err', color: '#dc143c' },
  breakpoint_tool_call: { label: 'Breakpoint', color: '#ff6b35' },
  breakpoint_action_complete: { label: 'BP Done', color: '#daa06d' },
  run_loop_cancelled: { label: 'Cancelled', color: '#8b8b8b' },
  run_loop_error: { label: 'Loop Err', color: '#dc143c' },
  shutdown_requested: { label: 'Shutdown', color: '#8b8b8b' },
  task_complete_call: { label: 'Task Done', color: '#50c878' },
  task_complete_call_duplicate: { label: 'Dup Complete', color: '#6b6560' },
  ping: { label: 'Ping', color: '#6b6560' },
  // Evaluation server events
  eval_start: { label: 'Eval Start', color: '#9b59b6' },
  eval_config: { label: 'Eval Config', color: '#8e44ad' },
  rollout_start: { label: 'Rollout', color: '#3498db' },
  rollout_complete: { label: 'Rollout Done', color: '#2980b9' },
  judge_start: { label: 'Judge', color: '#e67e22' },
  judge_complete: { label: 'Judge Done', color: '#d35400' },
  reflection_start: { label: 'Reflect', color: '#1abc9c' },
  reflection_complete: { label: 'Reflect Done', color: '#16a085' },
  reflection_error: { label: 'Reflect Err', color: '#dc143c' },
};
