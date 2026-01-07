'use client';

import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Scale, Sparkles } from 'lucide-react';
import type { AgentNodeData } from '@/types/mail';

interface AgentNodeProps {
  data: AgentNodeData;
  selected?: boolean;
}

// Colors for virtual node types
const VIRTUAL_COLORS = {
  judge: {
    border: '#e67e22',
    bg: 'rgba(230, 126, 34, 0.1)',
    glow: 'rgba(230, 126, 34, 0.4)',
    text: '#e67e22',
  },
  reflector: {
    border: '#1abc9c',
    bg: 'rgba(26, 188, 156, 0.1)',
    glow: 'rgba(26, 188, 156, 0.4)',
    text: '#1abc9c',
  },
};

function AgentNodeComponent({ data, selected }: AgentNodeProps) {
  const { name, isEntrypoint, canComplete, isInterswarm, isActive, eventCount, isVirtual, virtualType } = data;

  const virtualColor = virtualType ? VIRTUAL_COLORS[virtualType] : null;

  // Virtual node specific styles
  const virtualStyles = isVirtual && virtualColor ? {
    borderColor: isActive ? virtualColor.border : `${virtualColor.border}80`,
    backgroundColor: virtualColor.bg,
    borderStyle: 'dashed' as const,
    borderWidth: '2px',
    boxShadow: isActive ? `0 0 20px ${virtualColor.glow}` : undefined,
  } : {};

  return (
    <div
      className={`
        relative px-4 py-3 min-w-[140px]
        bg-card border border-border
        rounded transition-all duration-300
        ${!isVirtual && isActive ? 'forge-glow border-primary' : ''}
        ${selected ? 'border-gold shadow-[0_0_15px_rgba(207,181,59,0.3)]' : ''}
        hover:border-primary/40 hover:bg-secondary
        cursor-pointer
      `}
      style={virtualStyles}
    >
      {/* Connection handles */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2 !h-2 !bg-primary !border-background !border-2"
        style={isVirtual && virtualColor ? { backgroundColor: virtualColor.border } : undefined}
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!w-2 !h-2 !bg-primary !border-background !border-2"
        style={isVirtual && virtualColor ? { backgroundColor: virtualColor.border } : undefined}
      />

      {/* Activity indicator */}
      {isActive && (
        <div className="absolute -top-1 -right-1 w-3 h-3">
          <div
            className="absolute inset-0 rounded-full animate-ping opacity-75"
            style={{ backgroundColor: virtualColor?.border || 'var(--forge)' }}
          />
          <div
            className="absolute inset-0 rounded-full"
            style={{ backgroundColor: virtualColor?.border || 'var(--forge)' }}
          />
        </div>
      )}

      {/* Agent name with icon for virtual nodes */}
      <div
        className="font-mono text-sm font-semibold mb-2 tracking-wide flex items-center gap-2"
        style={{ color: virtualColor?.text || 'var(--foreground)' }}
      >
        {virtualType === 'judge' && <Scale className="w-4 h-4" />}
        {virtualType === 'reflector' && <Sparkles className="w-4 h-4" />}
        {name}
      </div>

      {/* Badges */}
      <div className="flex flex-wrap gap-1">
        {isVirtual && virtualType && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded font-medium uppercase tracking-wider"
            style={{
              backgroundColor: `${virtualColor?.border}20`,
              borderColor: `${virtualColor?.border}40`,
              borderWidth: '1px',
              color: virtualColor?.text,
            }}
          >
            {virtualType === 'judge' ? 'Evaluator' : 'GEPA'}
          </span>
        )}
        {isEntrypoint && (
          <span className="badge-entrypoint text-[10px] px-1.5 py-0.5 rounded font-medium uppercase tracking-wider">
            Entry
          </span>
        )}
        {canComplete && (
          <span className="badge-completer text-[10px] px-1.5 py-0.5 rounded font-medium uppercase tracking-wider">
            Completer
          </span>
        )}
        {isInterswarm && (
          <span className="text-[10px] px-1.5 py-0.5 rounded font-medium uppercase tracking-wider bg-bronze/20 border border-bronze/30 text-bronze">
            Inter
          </span>
        )}
      </div>

      {/* Event count */}
      {eventCount > 0 && (
        <div
          className="absolute -bottom-2 left-1/2 -translate-x-1/2 text-[9px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center"
          style={virtualColor ? {
            backgroundColor: virtualColor.border,
            color: '#fff',
          } : {
            backgroundColor: 'var(--primary)',
            color: 'var(--primary-foreground)',
          }}
        >
          {eventCount > 99 ? '99+' : eventCount}
        </div>
      )}

      {/* Metallic edge highlight (only for non-virtual nodes) */}
      {!isVirtual && (
        <div
          className="absolute inset-0 rounded pointer-events-none"
          style={{
            background: 'linear-gradient(135deg, rgba(205,127,50,0.1) 0%, transparent 50%, rgba(207,181,59,0.05) 100%)',
          }}
        />
      )}
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);
