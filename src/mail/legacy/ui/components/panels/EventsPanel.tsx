'use client';

import { useRef, useCallback, useEffect, useState } from 'react';
import {
  X,
  ChevronUp,
  ChevronDown,
  ChevronRight,
  Search,
  Filter,
  Trash2,
} from 'lucide-react';
import { useAppStore, useFilteredEvents } from '@/lib/store';
import { EVENT_TYPE_META, type EventType, type MAILEvent } from '@/types/mail';

function formatValue(value: unknown, depth = 0): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">null</span>;
  }
  if (typeof value === 'string') {
    // Truncate long strings
    if (value.length > 200) {
      return (
        <span className="text-green-400">
          "{value.slice(0, 200)}..."
        </span>
      );
    }
    return <span className="text-green-400">"{value}"</span>;
  }
  if (typeof value === 'number') {
    return <span className="text-blue-400">{value}</span>;
  }
  if (typeof value === 'boolean') {
    return <span className="text-yellow-400">{value ? 'true' : 'false'}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground">[]</span>;
    if (depth > 2) return <span className="text-muted-foreground">[...]</span>;
    return (
      <span className="text-muted-foreground">
        [{value.length} items]
      </span>
    );
  }
  if (typeof value === 'object') {
    const keys = Object.keys(value);
    if (keys.length === 0) return <span className="text-muted-foreground">{'{}'}</span>;
    if (depth > 2) return <span className="text-muted-foreground">{'...'}</span>;
    return (
      <span className="text-muted-foreground">
        {'{'}...{'}'}
      </span>
    );
  }
  return String(value);
}

function DataTable({ data, title }: { data: Record<string, unknown>; title?: string }) {
  // Handle case where data might be a string (parsing failed)
  if (typeof data === 'string') {
    return (
      <div className="mt-2">
        {title && (
          <div className="text-[10px] uppercase tracking-wider text-primary mb-1 font-medium">
            {title}
          </div>
        )}
        <pre className="bg-background/50 rounded border border-border/50 p-2 text-xs font-mono text-foreground/80 whitespace-pre-wrap">
          {data}
        </pre>
      </div>
    );
  }

  const entries = Object.entries(data).filter(([key]) => key !== 'caller');

  if (entries.length === 0) return null;

  return (
    <div className="mt-2">
      {title && (
        <div className="text-[10px] uppercase tracking-wider text-primary mb-1 font-medium">
          {title}
        </div>
      )}
      <div className="bg-background/50 rounded border border-border/50 overflow-hidden">
        <table className="w-full text-xs">
          <tbody>
            {entries.map(([key, value]) => (
              <tr key={key} className="border-b border-border/30 last:border-0">
                <td className="px-2 py-1.5 text-muted-foreground font-mono w-32 align-top">
                  {key}
                </td>
                <td className="px-2 py-1.5 font-mono break-all">
                  {typeof value === 'object' && value !== null && !Array.isArray(value) ? (
                    <pre className="text-[11px] whitespace-pre-wrap text-foreground/80 max-h-[150px] overflow-y-auto">
                      {JSON.stringify(value, null, 2)}
                    </pre>
                  ) : Array.isArray(value) ? (
                    <pre className="text-[11px] whitespace-pre-wrap text-foreground/80 max-h-[150px] overflow-y-auto">
                      {JSON.stringify(value, null, 2)}
                    </pre>
                  ) : (
                    formatValue(value)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Helper to get clean description for events
function getEventDescription(event: MAILEvent): { main: string; sub?: string } {
  // For new_message events, show sender → recipient with subject
  if (event.event === 'new_message' && event.extra_data?.full_message) {
    const msg = event.extra_data.full_message as {
      message?: {
        sender?: { address?: string };
        recipient?: { address?: string };
        recipients?: Array<{ address?: string }>;
        subject?: string;
        body?: string;
      };
      msg_type?: string;
    };

    const sender = msg.message?.sender?.address || 'unknown';
    const recipient = msg.message?.recipient?.address ||
      msg.message?.recipients?.[0]?.address || 'unknown';
    const subject = msg.message?.subject || '';
    const msgType = msg.msg_type || '';

    // Format: "Sender → Recipient"
    const main = `${sender} → ${recipient}`;
    // Show subject as subtitle, or message type
    const sub = subject && !subject.startsWith('::')
      ? subject
      : msgType ? `[${msgType}]` : undefined;

    return { main, sub };
  }

  // For tool_call events, use description but make it cleaner
  if (event.event === 'tool_call' && event.extra_data?.tool_name) {
    const toolName = event.extra_data.tool_name as string;
    const caller = event.extra_data.caller as string || 'agent';
    return {
      main: `${caller} called ${toolName}`,
      sub: undefined
    };
  }

  // Default: use description
  return { main: event.description };
}

function EventRow({ event }: { event: MAILEvent }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const meta = EVENT_TYPE_META[event.event] || { label: event.event, color: 'var(--muted-foreground)' };
  const { main: description, sub: subtitle } = getEventDescription(event);

  return (
    <div className="border-b border-border/50">
      {/* Header row - clickable */}
      <div
        className="flex items-start gap-3 px-4 py-2 hover:bg-primary/5 cursor-pointer group"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {/* Expand icon */}
        <div className="shrink-0 mt-0.5 text-muted-foreground">
          {isExpanded ? (
            <ChevronDown className="w-3 h-3" />
          ) : (
            <ChevronRight className="w-3 h-3" />
          )}
        </div>

        {/* Event type badge */}
        <div
          className="shrink-0 text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded mt-0.5"
          style={{
            backgroundColor: `${meta.color}15`,
            color: meta.color,
            borderColor: `${meta.color}30`,
            borderWidth: '1px',
          }}
        >
          {meta.label}
        </div>

        {/* Description */}
        <div className="flex-1 min-w-0">
          <p className={`text-sm text-foreground ${isExpanded ? '' : 'truncate'}`}>
            {description}
          </p>
          {subtitle && (
            <span className="text-[10px] text-muted-foreground">
              {subtitle}
            </span>
          )}
        </div>

        {/* Task ID */}
        <div className="shrink-0 text-[10px] text-muted-foreground font-mono opacity-0 group-hover:opacity-100 transition-opacity">
          {event.task_id.slice(0, 8)}
        </div>

        {/* Timestamp */}
        <div className="shrink-0 text-[10px] text-muted-foreground font-mono w-20 text-right">
          {new Date(event.timestamp).toLocaleTimeString()}
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="px-4 pb-3 pl-10 bg-card/30">
          {/* Basic info */}
          <DataTable
            title="Event Info"
            data={{
              event_type: event.event,
              task_id: event.task_id,
              timestamp: event.timestamp,
            }}
          />

          {/* Extra data */}
          {event.extra_data ? (
            typeof event.extra_data === 'object' && Object.keys(event.extra_data).filter(k => k !== 'caller').length > 0 ? (
              <DataTable
                title="Extra Data"
                data={event.extra_data as Record<string, unknown>}
              />
            ) : typeof event.extra_data === 'string' ? (
              <DataTable
                title="Extra Data (raw)"
                data={event.extra_data as unknown as Record<string, unknown>}
              />
            ) : (
              <div className="text-xs text-muted-foreground mt-2">
                Extra data: {JSON.stringify(event.extra_data)}
              </div>
            )
          ) : (
            <div className="text-xs text-muted-foreground mt-2">
              No extra data available
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FilterChip({
  type,
  active,
  onClick,
}: {
  type: EventType;
  active: boolean;
  onClick: () => void;
}) {
  const meta = EVENT_TYPE_META[type];
  if (!meta) return null;

  return (
    <button
      onClick={onClick}
      className={`
        text-[10px] font-medium uppercase tracking-wider px-2 py-1 rounded
        transition-all
        ${active
          ? 'opacity-100'
          : 'opacity-40 hover:opacity-70'
        }
      `}
      style={{
        backgroundColor: active ? `${meta.color}20` : 'transparent',
        color: meta.color,
        borderColor: `${meta.color}40`,
        borderWidth: '1px',
      }}
    >
      {meta.label}
    </button>
  );
}

export function EventsPanel() {
  const panelRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<HTMLDivElement>(null);

  const {
    isEventsPanelOpen,
    setEventsPanelOpen,
    eventsPanelHeight,
    setEventsPanelHeight,
    eventFilters,
    setEventFilters,
    clearEvents,
    events,
  } = useAppStore();

  const filteredEvents = useFilteredEvents();

  // Commonly used event types for filter chips
  const filterableTypes: EventType[] = [
    'new_message',
    'tool_call',
    'action_call',
    'task_complete',
    'task_error',
    'agent_error',
    // Evaluation events
    'judge_complete',
    'reflection_complete',
  ];

  // Resize handling
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const startY = e.clientY;
      const startHeight = eventsPanelHeight;

      const handleMouseMove = (e: MouseEvent) => {
        const delta = startY - e.clientY;
        setEventsPanelHeight(startHeight + delta);
      };

      const handleMouseUp = () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [eventsPanelHeight, setEventsPanelHeight]
  );

  // Auto-scroll to bottom
  useEffect(() => {
    if (panelRef.current && isEventsPanelOpen) {
      panelRef.current.scrollTop = panelRef.current.scrollHeight;
    }
  }, [filteredEvents, isEventsPanelOpen]);

  const toggleFilter = (type: EventType) => {
    const currentTypes = eventFilters.types;
    const newTypes = currentTypes.includes(type)
      ? currentTypes.filter((t) => t !== type)
      : [...currentTypes, type];

    setEventFilters({
      types: newTypes,
      showAll: newTypes.length === 0,
    });
  };

  // Toggle button when panel is closed
  if (!isEventsPanelOpen) {
    return (
      <button
        onClick={() => setEventsPanelOpen(true)}
        className="
          fixed bottom-0 left-1/2 -translate-x-1/2
          px-4 py-2 bg-card border border-border border-b-0
          rounded-t-lg
          flex items-center gap-2
          text-primary text-sm font-medium
          hover:bg-secondary
          transition-colors
          z-30
        "
      >
        <ChevronUp className="w-4 h-4" />
        Events
        {events.length > 0 && (
          <span className="bg-primary text-primary-foreground text-[10px] font-bold px-1.5 py-0.5 rounded-full">
            {events.length}
          </span>
        )}
      </button>
    );
  }

  return (
    <div
      className="fixed bottom-0 left-[320px] right-0 bg-sidebar border-t border-border shadow-2xl slide-in-up z-30"
      style={{ height: eventsPanelHeight }}
    >
      {/* Resize handle */}
      <div
        ref={resizeRef}
        className="absolute top-0 left-0 right-0 h-1 cursor-ns-resize hover:bg-primary/30 transition-colors"
        onMouseDown={handleMouseDown}
      />

      {/* Header */}
      <div className="flex items-center gap-4 px-4 py-2 border-b border-border">
        <button
          onClick={() => setEventsPanelOpen(false)}
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronDown className="w-5 h-5" />
        </button>

        <h2 className="font-sans font-bold text-foreground text-sm">
          EVENT STREAM
        </h2>

        <span className="text-xs text-muted-foreground font-mono">
          {filteredEvents.length} / {events.length}
        </span>

        {/* Search */}
        <div className="flex-1 max-w-xs relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search events..."
            value={eventFilters.search}
            onChange={(e) => setEventFilters({ search: e.target.value })}
            className="
              w-full pl-8 pr-3 py-1.5
              bg-card border border-border
              rounded text-xs text-foreground font-mono
              placeholder:text-muted-foreground
              focus:outline-none focus:border-primary
            "
          />
        </div>

        {/* Filter chips */}
        <div className="flex items-center gap-1">
          <Filter className="w-4 h-4 text-muted-foreground mr-1" />
          {filterableTypes.map((type) => (
            <FilterChip
              key={type}
              type={type}
              active={eventFilters.showAll || eventFilters.types.includes(type)}
              onClick={() => toggleFilter(type)}
            />
          ))}
        </div>

        {/* Clear button */}
        <button
          onClick={clearEvents}
          className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
          title="Clear events"
        >
          <Trash2 className="w-4 h-4" />
        </button>

        {/* Close button */}
        <button
          onClick={() => setEventsPanelOpen(false)}
          className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-secondary rounded transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Events list */}
      <div
        ref={panelRef}
        className="overflow-y-auto"
        style={{ height: 'calc(100% - 48px)' }}
      >
        {filteredEvents.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center">
              <div className="text-2xl mb-2">///</div>
              <p className="text-sm">
                {events.length === 0
                  ? 'No events yet'
                  : 'No events match your filters'}
              </p>
            </div>
          </div>
        ) : (
          filteredEvents.map((event) => (
            <EventRow key={event.id} event={event} />
          ))
        )}
      </div>
    </div>
  );
}
