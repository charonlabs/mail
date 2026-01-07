'use client';

import { useRef, useCallback, useEffect } from 'react';
import { X, Cpu, Wrench, MessageSquare, ArrowRight } from 'lucide-react';
import { useAppStore, useAgentTrace } from '@/lib/store';
import type { MAILEvent } from '@/types/mail';

// Component for displaying an incoming message to the agent
function IncomingMessageCard({ event }: { event: MAILEvent }) {
  const msg = event.extra_data?.full_message as {
    message?: {
      sender?: { address?: string };
      subject?: string;
      body?: string;
    };
    msg_type?: string;
  };

  const sender = msg?.message?.sender?.address || 'unknown';
  const subject = msg?.message?.subject || '';
  const body = msg?.message?.body || '';
  const msgType = msg?.msg_type || 'message';

  // Don't show task_complete broadcasts as inputs
  if (subject === '::task_complete::') return null;

  return (
    <div className="mb-6">
      {/* Message header */}
      <div className="flex items-center gap-2 mb-2">
        <MessageSquare className="w-4 h-4 text-gold" />
        <span className="text-xs text-gold font-medium uppercase tracking-wider">
          Incoming {msgType}
        </span>
        <span className="text-muted-foreground">from</span>
        <span className="text-sm font-medium text-foreground">{sender}</span>
        <span className="ml-auto text-[10px] text-muted-foreground font-mono">
          {new Date(event.timestamp).toLocaleTimeString()}
        </span>
      </div>

      {/* Message content */}
      <div className="border border-gold/30 rounded-lg overflow-hidden bg-gold/5">
        {subject && !subject.startsWith('::') && (
          <div className="px-3 py-2 bg-gold/10 border-b border-gold/20 text-sm font-medium text-gold">
            {subject}
          </div>
        )}
        <div className="p-3">
          <pre className="text-sm text-foreground whitespace-pre-wrap font-mono leading-relaxed">
            {body}
          </pre>
        </div>
      </div>
    </div>
  );
}

// Component for displaying a tool call made by the agent
function ToolCallCard({ event }: { event: MAILEvent }) {
  const toolName = event.extra_data?.tool_name as string;
  const toolArgs = event.extra_data?.tool_args as Record<string, unknown>;
  const reasoning = event.extra_data?.reasoning as string | undefined;

  // Format tool args nicely
  const formatArgValue = (value: unknown): string => {
    if (typeof value === 'string') {
      // Truncate long strings
      if (value.length > 500) {
        return value.slice(0, 500) + '...';
      }
      return value;
    }
    return JSON.stringify(value, null, 2);
  };

  return (
    <div className="mb-6">
      {/* Reasoning in italics */}
      {reasoning && (
        <div className="mb-3 text-sm text-muted-foreground italic leading-relaxed">
          {reasoning}
        </div>
      )}

      {/* Tool call box */}
      <div className="border border-primary/30 rounded-lg overflow-hidden bg-primary/5">
        {/* Tool name header */}
        <div className="flex items-center gap-2 px-3 py-2 bg-primary/10 border-b border-primary/20">
          <Wrench className="w-4 h-4 text-primary" />
          <span className="font-mono text-sm font-medium text-primary">
            {toolName}
          </span>
          <ArrowRight className="w-3 h-3 text-muted-foreground" />
          {toolArgs?.target !== undefined && toolArgs?.target !== null && (
            <span className="text-sm text-foreground">
              {String(toolArgs.target)}
            </span>
          )}
          <span className="ml-auto text-[10px] text-muted-foreground font-mono">
            {new Date(event.timestamp).toLocaleTimeString()}
          </span>
        </div>

        {/* Tool arguments */}
        {toolArgs && Object.keys(toolArgs).length > 0 && (
          <div className="p-3 space-y-2">
            {Object.entries(toolArgs).map(([key, value]) => (
              <div key={key} className="flex flex-col gap-1">
                <span className="text-xs text-muted-foreground font-mono">
                  {key}:
                </span>
                <div className="pl-3 border-l-2 border-primary/20">
                  {typeof value === 'string' && value.includes('\n') ? (
                    <pre className="text-sm text-foreground whitespace-pre-wrap font-mono leading-relaxed">
                      {formatArgValue(value)}
                    </pre>
                  ) : (
                    <span className="text-sm text-foreground font-mono">
                      {typeof value === 'string' ? (
                        <span className="text-green-400">"{formatArgValue(value)}"</span>
                      ) : (
                        <span className="text-blue-400">{formatArgValue(value)}</span>
                      )}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Render the appropriate card based on event type
function TraceEventCard({ event, agentName }: { event: MAILEvent; agentName: string }) {
  if (event.event === 'new_message') {
    return <IncomingMessageCard event={event} />;
  }
  if (event.event === 'tool_call' || event.event === 'builtin_tool_call') {
    return <ToolCallCard event={event} />;
  }
  return null;
}

export function AgentDetailPanel() {
  const panelRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<HTMLDivElement>(null);

  const {
    selectedAgent,
    setSelectedAgent,
    isDetailPanelOpen,
    setDetailPanelOpen,
    detailPanelWidth,
    setDetailPanelWidth,
    agents,
    activeAgents,
  } = useAppStore();

  // Use the new trace hook that gets both incoming messages and tool calls
  const traceEvents = useAgentTrace(selectedAgent);

  // Get agent info
  const agent = agents.find((a) => a.name === selectedAgent);
  const isActive = selectedAgent ? activeAgents.has(selectedAgent) : false;

  // Resize handling
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = detailPanelWidth;

      const handleMouseMove = (e: MouseEvent) => {
        const delta = startX - e.clientX;
        setDetailPanelWidth(startWidth + delta);
      };

      const handleMouseUp = () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [detailPanelWidth, setDetailPanelWidth]
  );

  // Auto-scroll to bottom on new events
  useEffect(() => {
    if (panelRef.current) {
      panelRef.current.scrollTop = panelRef.current.scrollHeight;
    }
  }, [traceEvents]);

  const handleClose = () => {
    setDetailPanelOpen(false);
    setSelectedAgent(null);
  };

  if (!isDetailPanelOpen || !selectedAgent) return null;

  // Count stats
  const messageCount = traceEvents.filter(e => e.event === 'new_message').length;
  const toolCallCount = traceEvents.filter(e => e.event === 'tool_call' || e.event === 'builtin_tool_call').length;

  return (
    <div
      className="fixed top-0 right-0 h-full bg-sidebar border-l border-border shadow-2xl slide-in-right z-40"
      style={{ width: detailPanelWidth }}
    >
      {/* Resize handle */}
      <div
        ref={resizeRef}
        className="resize-handle"
        onMouseDown={handleMouseDown}
      />

      {/* Header */}
      <div className="p-4 border-b border-border flex items-center gap-3">
        <div
          className={`
            w-10 h-10 rounded flex items-center justify-center
            ${isActive ? 'forge-glow bg-forge/20' : 'bg-card'}
            border border-border
          `}
        >
          <Cpu className={`w-5 h-5 ${isActive ? 'text-forge' : 'text-primary'}`} />
        </div>

        <div className="flex-1 min-w-0">
          <h2 className="font-sans font-bold text-foreground truncate">
            {selectedAgent}
          </h2>
          <div className="flex items-center gap-2 mt-1">
            {agent?.enable_entrypoint && (
              <span className="badge-entrypoint text-[10px] px-1.5 py-0.5 rounded">
                ENTRY
              </span>
            )}
            {agent?.can_complete_tasks && (
              <span className="badge-completer text-[10px] px-1.5 py-0.5 rounded">
                COMPLETER
              </span>
            )}
            {isActive && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-forge/20 border border-forge/30 text-forge">
                ACTIVE
              </span>
            )}
          </div>
        </div>

        <button
          onClick={handleClose}
          className="w-8 h-8 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Comm targets */}
      {agent && agent.comm_targets.length > 0 && (
        <div className="px-4 py-2 border-b border-border">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Communicates with
          </div>
          <div className="flex flex-wrap gap-1">
            {agent.comm_targets.map((target) => (
              <button
                key={target}
                onClick={() => setSelectedAgent(target)}
                className="text-xs px-2 py-1 rounded bg-secondary text-primary hover:bg-accent transition-colors"
              >
                {target}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Trace stream */}
      <div
        ref={panelRef}
        className="flex-1 overflow-y-auto p-4"
        style={{ height: 'calc(100% - 140px)' }}
      >
        {traceEvents.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <div className="text-2xl mb-2">~</div>
            <p className="text-sm">No activity yet for this agent</p>
          </div>
        ) : (
          traceEvents.map((event) => (
            <TraceEventCard key={event.id} event={event} agentName={selectedAgent} />
          ))
        )}
      </div>

      {/* Footer stats */}
      <div className="p-3 border-t border-border text-xs text-muted-foreground font-mono flex gap-4">
        <span>{messageCount} messages</span>
        <span>{toolCallCount} tool calls</span>
      </div>
    </div>
  );
}
