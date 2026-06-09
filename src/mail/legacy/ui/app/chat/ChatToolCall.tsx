'use client';

import { useState, useEffect } from 'react';
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
} from '@/components/ai-elements/tool';
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from '@/components/ai-elements/reasoning';
import type { EnrichedToolCall } from '@/hooks/useChatTimeline';

interface ChatToolCallProps {
  toolCall: EnrichedToolCall;
  isRunning?: boolean;
}

export function ChatToolCall({ toolCall, isRunning = false }: ChatToolCallProps) {
  const { event, result, hasResult } = toolCall;

  const toolName = (event.extra_data?.tool_name as string) ?? 'unknown';
  const toolArgs = (event.extra_data?.tool_args as Record<string, unknown>) ?? {};
  const rawReasoning = event.extra_data?.reasoning;
  const timestamp = new Date(event.timestamp);

  // Reasoning can be a string or array of strings
  const reasoningText = rawReasoning
    ? Array.isArray(rawReasoning)
      ? rawReasoning.join('\n')
      : String(rawReasoning)
    : null;

  // Map to Tool component state
  const state = isRunning ? 'input-available' : 'output-available';

  // Auto-expand when result arrives
  const [isOpen, setIsOpen] = useState(false);
  useEffect(() => {
    if (hasResult) {
      setIsOpen(true);
    }
  }, [hasResult]);

  return (
    <div className="my-3">
      {/* Reasoning in collapsible component */}
      {reasoningText && (
        <Reasoning
          isStreaming={isRunning}
          defaultOpen={false}
          className="mb-2"
        >
          <ReasoningTrigger />
          <ReasoningContent>{reasoningText}</ReasoningContent>
        </Reasoning>
      )}

      {/* Tool card */}
      <Tool open={isOpen} onOpenChange={setIsOpen}>
        <ToolHeader
          title={toolName}
          type="tool-invocation"
          state={state}
        />
        <ToolContent>
          <div className="flex justify-end text-xs text-muted-foreground px-4 pt-2">
            {timestamp.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
          <ToolInput input={toolArgs} />
          {hasResult && (
            <ToolOutput output={result} errorText={undefined} />
          )}
        </ToolContent>
      </Tool>
    </div>
  );
}
