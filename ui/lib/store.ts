import { create } from 'zustand';
import type {
  Agent,
  MAILEvent,
  ChatMessage,
  ConnectionStatus,
  EventFilters,
  EventType,
} from '@/types/mail';

interface AppState {
  // Connection
  serverUrl: string;
  connectionStatus: ConnectionStatus;
  setServerUrl: (url: string) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;

  // Agents
  agents: Agent[];
  entrypoint: string;
  activeAgents: Set<string>;
  selectedAgent: string | null;
  agentLastViewed: Record<string, number>; // timestamp when agent was last viewed
  setAgents: (agents: Agent[], entrypoint: string) => void;
  setActiveAgent: (name: string, active: boolean) => void;
  setSelectedAgent: (name: string | null) => void;
  markAgentViewed: (name: string) => void;

  // Events
  events: MAILEvent[];
  eventFilters: EventFilters;
  addEvent: (event: MAILEvent) => void;
  clearEvents: () => void;
  setEventFilters: (filters: Partial<EventFilters>) => void;

  // Chat
  messages: ChatMessage[];
  currentTaskId: string | null;
  isProcessing: boolean;
  addMessage: (message: ChatMessage) => void;
  replaceUserMessageForTask: (taskId: string, content: string, timestamp?: string) => void;
  setCurrentTaskId: (taskId: string | null) => void;
  setIsProcessing: (processing: boolean) => void;

  // Panels
  isDetailPanelOpen: boolean;
  isEventsPanelOpen: boolean;
  detailPanelWidth: number;
  eventsPanelHeight: number;
  setDetailPanelOpen: (open: boolean) => void;
  setEventsPanelOpen: (open: boolean) => void;
  setDetailPanelWidth: (width: number) => void;
  setEventsPanelHeight: (height: number) => void;

  // Eval Mode
  isEvalMode: boolean;
  evalConfig: EvalConfig;
  setEvalMode: (enabled: boolean) => void;
  setEvalConfig: (config: Partial<EvalConfig>) => void;
}

export interface EvalConfig {
  evalSet: string;
  qIdx: number;
  modelId: string;
  reflectorModel: string;
  passThreshold: number;
  runReflection: boolean;
}

export const useAppStore = create<AppState>((set, get) => ({
  // Connection
  serverUrl: process.env.NEXT_PUBLIC_MAIL_SERVER_URL || 'http://localhost:8000',
  connectionStatus: 'disconnected',
  setServerUrl: (url) => set({ serverUrl: url }),
  setConnectionStatus: (status) => set({ connectionStatus: status }),

  // Agents
  agents: [],
  entrypoint: '',
  activeAgents: new Set(),
  selectedAgent: null,
  agentLastViewed: {},
  setAgents: (agents, entrypoint) => set({ agents, entrypoint }),
  setActiveAgent: (name, active) =>
    set((state) => {
      const newActive = new Set(state.activeAgents);
      if (active) {
        newActive.add(name);
      } else {
        newActive.delete(name);
      }
      return { activeAgents: newActive };
    }),
  setSelectedAgent: (name) =>
    set((state) => ({
      selectedAgent: name,
      isDetailPanelOpen: name !== null,
      // Mark agent as viewed when selected
      agentLastViewed: name
        ? { ...state.agentLastViewed, [name]: Date.now() }
        : state.agentLastViewed,
    })),
  markAgentViewed: (name) =>
    set((state) => ({
      agentLastViewed: { ...state.agentLastViewed, [name]: Date.now() },
    })),

  // Events
  events: [],
  eventFilters: {
    search: '',
    types: [],
    showAll: true,
  },
  addEvent: (event) =>
    set((state) => {
      // Skip ping events from display
      if (event.event === 'ping') return state;

      console.log('[Store] addEvent received:', event.event, 'extra_data:', event.extra_data);

      // Extract agent name from description (e.g., "agent Supervisor called...")
      // Supports agent names with hyphens, dots, and underscores (e.g., "Agent-1", "my.agent")
      let caller = event.extra_data?.caller as string | undefined;
      if (!caller && event.description) {
        // Match agent name: alphanumeric plus hyphens, dots, underscores
        // Stops at common verbs or whitespace patterns
        const match = event.description.match(/^agent ([\w.-]+)/i);
        if (match) {
          caller = match[1];
        }
      }

      // Create new event with caller in extra_data
      const newEvent = {
        ...event,
        extra_data: { ...event.extra_data, caller },
      };

      // Track active agents based on events (both callers and recipients)
      const newActiveAgents = new Set(state.activeAgents);

      // Helper to mark agent active with timeout
      const markAgentActive = (agentName: string) => {
        newActiveAgents.add(agentName);
        // Clear active state after 3 seconds of no activity
        setTimeout(() => {
          const store = get();
          // Check if agent has recent activity as caller or recipient
          const recentEvents = store.events.filter((e) => {
            const eventTime = Date.now() - new Date(e.timestamp).getTime();
            if (eventTime >= 3000) return false;

            // Check caller
            if (e.extra_data?.caller === agentName) return true;

            // Check recipient for messages
            if (e.event === 'new_message' && e.extra_data?.full_message) {
              const msg = e.extra_data.full_message as {
                message?: {
                  recipient?: { address?: string };
                  recipients?: Array<{ address?: string }>;
                };
              };
              const recipient = msg.message?.recipient?.address;
              const recipients = msg.message?.recipients?.map(r => r.address) || [];
              if (recipient === agentName || recipients.includes(agentName)) return true;
            }
            return false;
          });
          if (recentEvents.length === 0) {
            store.setActiveAgent(agentName, false);
          }
        }, 3000);
      };

      // Mark caller as active
      if (caller && typeof caller === 'string') {
        markAgentActive(caller);
      }

      // Mark recipients as active for messages
      if (newEvent.event === 'new_message' && newEvent.extra_data) {
        const fullMsg = (newEvent.extra_data as Record<string, unknown>).full_message as {
          message?: {
            recipient?: { address?: string };
            recipients?: Array<{ address?: string }>;
          };
        } | undefined;
        if (fullMsg) {
          const recipient = fullMsg.message?.recipient?.address;
          const recipients = fullMsg.message?.recipients?.map(r => r.address) || [];

          if (recipient) markAgentActive(recipient);
          recipients.forEach(r => {
            if (r) markAgentActive(r);
          });
        }
      }

      return {
        events: [...state.events, newEvent].slice(-1000), // Keep last 1000 events
        activeAgents: newActiveAgents,
      };
    }),
  clearEvents: () => set({ events: [] }),
  setEventFilters: (filters) =>
    set((state) => ({
      eventFilters: { ...state.eventFilters, ...filters },
    })),

  // Chat
  messages: [],
  currentTaskId: null,
  isProcessing: false,
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
  replaceUserMessageForTask: (taskId, content, timestamp) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.role === 'user' && message.task_id === taskId
          ? { ...message, content, timestamp: timestamp ?? message.timestamp }
          : message
      ),
    })),
  setCurrentTaskId: (taskId) => set({ currentTaskId: taskId }),
  setIsProcessing: (processing) => set({ isProcessing: processing }),

  // Panels
  isDetailPanelOpen: false,
  isEventsPanelOpen: false,
  detailPanelWidth: 450,
  eventsPanelHeight: 300,
  setDetailPanelOpen: (open) => set({ isDetailPanelOpen: open }),
  setEventsPanelOpen: (open) => set({ isEventsPanelOpen: open }),
  setDetailPanelWidth: (width) => set({ detailPanelWidth: Math.max(300, Math.min(800, width)) }),
  setEventsPanelHeight: (height) => set({ eventsPanelHeight: Math.max(150, Math.min(500, height)) }),

  // Eval Mode
  isEvalMode: false,
  evalConfig: {
    evalSet: 'hard_questions',
    qIdx: 0,
    modelId: 'anthropic/claude-sonnet-4-5-20250929',
    reflectorModel: 'claude-opus-4-5-20251101',
    passThreshold: 0.75,
    runReflection: true,
  },
  setEvalMode: (enabled) => set({ isEvalMode: enabled }),
  setEvalConfig: (config) =>
    set((state) => ({
      evalConfig: { ...state.evalConfig, ...config },
    })),
}));

// Selectors
export const useFilteredEvents = () => {
  const events = useAppStore((s) => s.events);
  const filters = useAppStore((s) => s.eventFilters);

  return events.filter((event) => {
    // Filter by search
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      const matchesSearch =
        event.description.toLowerCase().includes(searchLower) ||
        event.event.toLowerCase().includes(searchLower) ||
        event.task_id.toLowerCase().includes(searchLower) ||
        JSON.stringify(event.extra_data).toLowerCase().includes(searchLower);
      if (!matchesSearch) return false;
    }

    // Filter by type
    if (!filters.showAll && filters.types.length > 0) {
      if (!filters.types.includes(event.event)) return false;
    }

    return true;
  });
};

export const useAgentEvents = (agentName: string | null) => {
  const events = useAppStore((s) => s.events);

  if (!agentName) return [];

  return events.filter((event) => {
    const caller = event.extra_data?.caller;
    return caller === agentName;
  });
};

// Check if an agent has unseen activity (events newer than last viewed)
export const useAgentHasUnseenActivity = (agentName: string | null) => {
  const events = useAppStore((s) => s.events);
  const agentLastViewed = useAppStore((s) => s.agentLastViewed);

  if (!agentName) return false;

  const lastViewed = agentLastViewed[agentName] || 0;

  // Check for any events related to this agent that are newer than last viewed
  return events.some((event) => {
    const eventTime = new Date(event.timestamp).getTime();
    if (eventTime <= lastViewed) return false;

    // Check if agent is the caller (tool calls)
    if (event.extra_data?.caller === agentName) return true;

    // Check if agent is the recipient (messages)
    if (event.event === 'new_message' && event.extra_data?.full_message) {
      const msg = event.extra_data.full_message as {
        message?: {
          recipient?: { address?: string };
          recipients?: Array<{ address?: string }>;
        };
      };
      const recipient = msg.message?.recipient?.address;
      const recipients = msg.message?.recipients?.map(r => r.address) || [];
      if (recipient === agentName || recipients.includes(agentName)) return true;
    }

    return false;
  });
};

// Get all events relevant to an agent (both sent BY and received BY)
export const useAgentTrace = (agentName: string | null) => {
  const events = useAppStore((s) => s.events);

  if (!agentName) return [];

  return events.filter((event) => {
    // Tool calls made BY this agent
    if (event.event === 'tool_call' || event.event === 'builtin_tool_call') {
      return event.extra_data?.caller === agentName;
    }

    // Messages sent TO this agent
    if (event.event === 'new_message' && event.extra_data?.full_message) {
      const msg = event.extra_data.full_message as {
        message?: {
          recipient?: { address?: string };
          recipients?: Array<{ address?: string }>;
        };
      };
      const recipient = msg.message?.recipient?.address;
      const recipients = msg.message?.recipients?.map(r => r.address) || [];
      return recipient === agentName || recipients.includes(agentName);
    }

    // Eval events (judge and reflection) - attributed by caller
    if (
      event.event === 'judge_start' ||
      event.event === 'judge_complete' ||
      event.event === 'reflection_start' ||
      event.event === 'reflection_complete' ||
      event.event === 'reflection_error'
    ) {
      return event.extra_data?.caller === agentName;
    }

    return false;
  });
};
