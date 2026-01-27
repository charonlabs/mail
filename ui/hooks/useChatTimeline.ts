import { useMemo } from 'react';
import { useAppStore } from '@/lib/store';
import type { ChatMessage, MAILEvent } from '@/types/mail';

/** Tool call with optional result from action_complete */
export interface EnrichedToolCall {
  event: MAILEvent;
  result?: string;
  hasResult: boolean;
}

/** Message with optional reasoning from task_complete */
export interface EnrichedMessage {
  message: ChatMessage;
  reasoning?: string;
}

export type TimelineItem =
  | { type: 'message'; data: EnrichedMessage; timestamp: Date }
  | { type: 'tool_call'; data: EnrichedToolCall; timestamp: Date }
  | { type: 'error'; data: MAILEvent; timestamp: Date };

/**
 * Hook that merges chat messages, tool call events, and errors into a unified timeline.
 * - Filters tool_call events from the supervisor/entrypoint agent
 * - Merges action_complete results into matching tool_call items by tool_call_id
 * - Includes action_error events as separate error items
 */
export function useChatTimeline(): TimelineItem[] {
  const messages = useAppStore((s) => s.messages);
  const events = useAppStore((s) => s.events);
  const currentTaskId = useAppStore((s) => s.currentTaskId);
  const entrypoint = useAppStore((s) => s.entrypoint) || 'supervisor';

  return useMemo(() => {
    // Filter tool_call events from entrypoint for current task
    // Exclude task_complete since we attach its reasoning to the final message
    const toolCallEvents = events.filter((e) => {
      if (e.event !== 'tool_call') return false;
      if (e.task_id !== currentTaskId) return false;

      const caller = e.extra_data?.caller as string | undefined;
      if (!caller) return false;

      // Match if caller starts with entrypoint (handles supervisor vs supervisor_0)
      if (!caller.startsWith(entrypoint)) return false;

      // Exclude task_complete tool calls
      const toolName = e.extra_data?.tool_name as string | undefined;
      if (toolName === 'task_complete') return false;

      return true;
    });

    // Find task_complete reasoning to attach to assistant messages
    const taskCompleteEvent = events.find(
      (e) =>
        e.event === 'tool_call' &&
        e.task_id === currentTaskId &&
        e.extra_data?.tool_name === 'task_complete'
    );
    const taskCompleteReasoning = taskCompleteEvent?.extra_data?.reasoning;
    const reasoningText = taskCompleteReasoning
      ? Array.isArray(taskCompleteReasoning)
        ? taskCompleteReasoning.join('\n')
        : String(taskCompleteReasoning)
      : undefined;

    // Build a map of tool_call_id -> action_complete result
    const resultMap = new Map<string, string>();
    events
      .filter((e) => e.event === 'action_complete' && e.task_id === currentTaskId)
      .forEach((e) => {
        const toolCallId = e.extra_data?.tool_call_id as string | undefined;
        const result = e.extra_data?.result as string | undefined;
        if (toolCallId && result) {
          resultMap.set(toolCallId, result);
        }
      });

    // Filter action_error events for current task
    const errorEvents = events.filter(
      (e) => e.event === 'action_error' && e.task_id === currentTaskId
    );

    // Map messages to timeline items, attaching task_complete reasoning to assistant messages
    const messageItems: TimelineItem[] = messages.map((m) => ({
      type: 'message' as const,
      data: {
        message: m,
        // Attach reasoning to assistant messages (the final response)
        reasoning: m.role === 'assistant' ? reasoningText : undefined,
      },
      timestamp: new Date(m.timestamp),
    }));

    // Map tool calls to timeline items, enriching with results
    const toolCallItems: TimelineItem[] = toolCallEvents.map((e) => {
      const toolCallId = e.extra_data?.tool_call_id as string | undefined;
      const result = toolCallId ? resultMap.get(toolCallId) : undefined;

      return {
        type: 'tool_call' as const,
        data: {
          event: e,
          result,
          hasResult: result !== undefined,
        },
        timestamp: new Date(e.timestamp),
      };
    });

    // Map errors to timeline items
    const errorItems: TimelineItem[] = errorEvents.map((e) => ({
      type: 'error' as const,
      data: e,
      timestamp: new Date(e.timestamp),
    }));

    // Merge and sort by timestamp
    return [...messageItems, ...toolCallItems, ...errorItems].sort(
      (a, b) => a.timestamp.getTime() - b.timestamp.getTime()
    );
  }, [messages, events, currentTaskId, entrypoint]);
}
