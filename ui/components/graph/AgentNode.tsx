'use client';

import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Scale, Sparkles, Eye } from 'lucide-react';
import type { AgentNodeData } from '@/types/mail';

interface AgentNodeProps {
  data: AgentNodeData;
  selected?: boolean;
}

// Colors for virtual node types (normal mode)
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

// Eval mode colors - more dramatic
const EVAL_VIRTUAL_COLORS = {
  judge: {
    border: '#ffaa00',  // Amber for The Arbiter
    bg: 'rgba(255, 170, 0, 0.08)',
    glow: 'rgba(255, 170, 0, 0.5)',
    text: '#ffaa00',
  },
  reflector: {
    border: '#00ffff',  // Cyan for The Oracle
    bg: 'rgba(0, 255, 255, 0.06)',
    glow: 'rgba(0, 255, 255, 0.5)',
    text: '#00ffff',
  },
};

function AgentNodeComponent({ data, selected }: AgentNodeProps) {
  const { name, isEntrypoint, canComplete, isInterswarm, isActive, eventCount, isVirtual, virtualType, isEvalMode } = data;

  // Use eval mode colors when in eval mode
  const colorPalette = isEvalMode ? EVAL_VIRTUAL_COLORS : VIRTUAL_COLORS;
  const virtualColor = virtualType ? colorPalette[virtualType] : null;

  // Virtual node specific styles
  const virtualStyles = isVirtual && virtualColor ? {
    borderColor: isActive ? virtualColor.border : `${virtualColor.border}80`,
    backgroundColor: virtualColor.bg,
    borderStyle: 'dashed' as const,
    borderWidth: '2px',
    boxShadow: isActive
      ? `0 0 20px ${virtualColor.glow}, 0 0 40px ${virtualColor.glow}40`
      : undefined,
  } : {};

  // Determine badge text - more dramatic in eval mode
  const getBadgeText = () => {
    if (!isVirtual || !virtualType) return null;
    if (isEvalMode) {
      return virtualType === 'judge' ? 'THE ARBITER' : 'THE ORACLE';
    }
    return virtualType === 'judge' ? 'Evaluator' : 'GEPA';
  };

  // Display name - can be more dramatic in eval mode
  const getDisplayName = () => {
    if (isEvalMode && virtualType === 'judge') return 'JUDGE';
    if (isEvalMode && virtualType === 'reflector') return 'REFLECTOR';
    return name;
  };

  return (
    <div
      className={`
        relative px-4 py-3 min-w-[140px]
        bg-card border border-border
        rounded transition-all duration-300
        ${!isVirtual && isActive ? 'forge-glow border-primary' : ''}
        ${selected ? 'border-gold shadow-[0_0_15px_rgba(207,181,59,0.3)]' : ''}
        ${isEvalMode && isVirtual && virtualType === 'judge' && isActive ? 'judge-active' : ''}
        ${isEvalMode && isVirtual && virtualType === 'reflector' && isActive ? 'reflector-active' : ''}
        hover:border-primary/40 hover:bg-secondary
        cursor-pointer
      `}
      style={virtualStyles}
    >
      {/* Pulsing rings for Judge when active in eval mode */}
      {isEvalMode && virtualType === 'judge' && isActive && (
        <>
          <div
            className="absolute inset-0 rounded animate-ping opacity-20"
            style={{ borderWidth: '2px', borderStyle: 'solid', borderColor: virtualColor?.border }}
          />
          <div
            className="absolute -inset-2 rounded animate-pulse opacity-10"
            style={{ borderWidth: '1px', borderStyle: 'dashed', borderColor: virtualColor?.border }}
          />
        </>
      )}

      {/* Breathing effect for Reflector when active in eval mode */}
      {isEvalMode && virtualType === 'reflector' && isActive && (
        <div
          className="absolute inset-0 rounded pointer-events-none"
          style={{
            background: `radial-gradient(ellipse at center, ${virtualColor?.glow}30 0%, transparent 70%)`,
            animation: 'reflector-breathe 2s ease-in-out infinite',
          }}
        />
      )}

      {/* Connection handles */}
      <Handle
        type="target"
        position={Position.Left}
        id="target-left"
        className="!w-2 !h-2 !bg-primary !border-background !border-2 opacity-0"
        style={isVirtual && virtualColor ? { backgroundColor: virtualColor.border } : undefined}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="source-right"
        className="!w-2 !h-2 !bg-primary !border-background !border-2 opacity-0"
        style={isVirtual && virtualColor ? { backgroundColor: virtualColor.border } : undefined}
      />
      <Handle
        type="target"
        position={Position.Top}
        id="target-top"
        className="!w-2 !h-2 !bg-primary !border-background !border-2 opacity-0"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="source-bottom"
        className="!w-2 !h-2 !bg-primary !border-background !border-2 opacity-0"
      />
      <Handle
        type="target"
        position={Position.Right}
        id="target-right"
        className="!w-2 !h-2 !bg-primary !border-background !border-2 opacity-0"
      />
      <Handle
        type="source"
        position={Position.Left}
        id="source-left"
        className="!w-2 !h-2 !bg-primary !border-background !border-2 opacity-0"
      />
      <Handle
        type="target"
        position={Position.Bottom}
        id="target-bottom"
        className="!w-2 !h-2 !bg-primary !border-background !border-2 opacity-0"
      />
      <Handle
        type="source"
        position={Position.Top}
        id="source-top"
        className="!w-2 !h-2 !bg-primary !border-background !border-2 opacity-0"
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
        className={`font-mono text-sm font-semibold mb-2 tracking-wide flex items-center gap-2 ${isEvalMode && isVirtual ? 'glitch-text' : ''}`}
        style={{ color: virtualColor?.text || 'var(--foreground)' }}
      >
        {virtualType === 'judge' && <Scale className="w-4 h-4" />}
        {virtualType === 'reflector' && (isEvalMode ? <Eye className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />)}
        {getDisplayName()}
      </div>

      {/* Badges */}
      <div className="flex flex-wrap gap-1">
        {isVirtual && virtualType && (
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded font-medium uppercase tracking-wider ${isEvalMode ? 'border' : ''}`}
            style={{
              backgroundColor: `${virtualColor?.border}20`,
              borderColor: `${virtualColor?.border}60`,
              color: virtualColor?.text,
              textShadow: isEvalMode ? `0 0 5px ${virtualColor?.border}` : undefined,
            }}
          >
            {getBadgeText()}
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
            color: '#000',
            boxShadow: isEvalMode ? `0 0 10px ${virtualColor.border}` : undefined,
          } : {
            backgroundColor: 'var(--primary)',
            color: 'var(--primary-foreground)',
          }}
        >
          {eventCount > 99 ? '99+' : eventCount}
        </div>
      )}

      {/* Metallic/Matrix edge highlight (non-virtual nodes) */}
      {!isVirtual && (
        <div
          className="absolute inset-0 rounded pointer-events-none"
          style={{
            background: isEvalMode
              ? 'linear-gradient(135deg, rgba(0,255,65,0.1) 0%, transparent 50%, rgba(0,255,255,0.05) 100%)'
              : 'linear-gradient(135deg, rgba(205,127,50,0.1) 0%, transparent 50%, rgba(207,181,59,0.05) 100%)',
          }}
        />
      )}
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);
