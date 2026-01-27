'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { useAppStore } from '@/lib/store';
import { Skull, Radio, Zap, Shield, Activity } from 'lucide-react';

interface EvalModeHeaderProps {
  connectionStartTime: number;
  superBreachMode?: boolean;
}

// Hidden messages that flash occasionally
const HIDDEN_MESSAGES = [
  '> THEY\'RE WATCHING',
  '> TRUST NO ONE',
  '> THE CAKE IS A LIE',
  '> 01001000 01001001',
  '> FOLLOW THE WHITE RABBIT',
  '> WAKE UP NEO',
  '> I KNOW KUNG FU',
  '> THERE IS NO SPOON',
  '> KNOCK KNOCK',
  '> SYSTEM FAILURE IMMINENT',
  '> HELLO RYAN',
];

// Characters for glitch effect
const GLITCH_CHARS = '!@#$%^&*()_+-=[]{}|;:,.<>?0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';

function GlitchText({ text, glitchProbability = 0.02 }: { text: string; glitchProbability?: number }) {
  const [displayText, setDisplayText] = useState(text);
  const [isGlitching, setIsGlitching] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      if (Math.random() < glitchProbability) {
        setIsGlitching(true);
        // Glitch for 100-300ms
        const glitchDuration = 100 + Math.random() * 200;

        // Create glitched version
        const glitched = text.split('').map(char =>
          Math.random() < 0.3 ? GLITCH_CHARS[Math.floor(Math.random() * GLITCH_CHARS.length)] : char
        ).join('');
        setDisplayText(glitched);

        setTimeout(() => {
          setDisplayText(text);
          setIsGlitching(false);
        }, glitchDuration);
      }
    }, 500);

    return () => clearInterval(interval);
  }, [text, glitchProbability]);

  return (
    <span className={isGlitching ? 'glitch-text' : ''}>
      {displayText}
    </span>
  );
}

function formatUptime(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  const s = seconds % 60;
  const m = minutes % 60;
  const h = hours;

  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function formatCycles(n: number): string {
  return n.toLocaleString();
}

export function EvalModeHeader({ connectionStartTime, superBreachMode = false }: EvalModeHeaderProps) {
  const { agents, events } = useAppStore();
  const [uptime, setUptime] = useState(0);
  const [cycles, setCycles] = useState(1337420);
  const [hiddenMessage, setHiddenMessage] = useState<string | null>(null);
  const [criticalDuration, setCriticalDuration] = useState(0);
  const criticalStartRef = useRef<number | null>(null);

  // Determine threat level based on recent events
  const threatLevel = useMemo(() => {
    const recentEvents = events.slice(-20);
    const hasError = recentEvents.some(e =>
      e.event === 'task_error' || e.event === 'agent_error' || e.event === 'reflection_error'
    );
    const hasJudge = recentEvents.some(e =>
      e.event === 'judge_start' || e.event === 'judge_complete'
    );
    const hasActivity = recentEvents.some(e =>
      e.event === 'tool_call' || e.event === 'new_message'
    );

    if (hasError || hasJudge) return 'CRITICAL';
    if (hasActivity) return 'ELEVATED';
    return 'NOMINAL';
  }, [events]);

  // Count active agents (those with recent events)
  const activeAgentCount = useMemo(() => {
    const recentCallers = new Set<string>();
    events.slice(-50).forEach(e => {
      if (e.extra_data?.caller) {
        recentCallers.add(e.extra_data.caller as string);
      }
    });
    return recentCallers.size;
  }, [events]);

  // Update uptime counter
  useEffect(() => {
    const interval = setInterval(() => {
      setUptime(Date.now() - connectionStartTime);
    }, 1000);
    return () => clearInterval(interval);
  }, [connectionStartTime]);

  // Update cycles counter (fake but fun)
  useEffect(() => {
    const interval = setInterval(() => {
      setCycles(prev => prev + Math.floor(Math.random() * 1000) + 100);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  // Track critical duration for easter egg
  useEffect(() => {
    if (threatLevel === 'CRITICAL') {
      if (!criticalStartRef.current) {
        criticalStartRef.current = Date.now();
      }
      const interval = setInterval(() => {
        setCriticalDuration(Date.now() - (criticalStartRef.current || Date.now()));
      }, 1000);
      return () => clearInterval(interval);
    } else {
      criticalStartRef.current = null;
      setCriticalDuration(0);
    }
  }, [threatLevel]);

  // Hidden messages that flash occasionally
  useEffect(() => {
    const interval = setInterval(() => {
      // 5% chance to show a hidden message
      if (Math.random() < 0.05) {
        // Special message if critical for 60+ seconds
        if (criticalDuration > 60000 && Math.random() < 0.3) {
          setHiddenMessage('> ARE YOU OKAY?');
        } else {
          setHiddenMessage(HIDDEN_MESSAGES[Math.floor(Math.random() * HIDDEN_MESSAGES.length)]);
        }

        // Hide after 1-2 seconds
        setTimeout(() => {
          setHiddenMessage(null);
        }, 1000 + Math.random() * 1000);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [criticalDuration]);

  const threatClass = threatLevel === 'CRITICAL'
    ? 'threat-critical'
    : threatLevel === 'ELEVATED'
      ? 'threat-elevated'
      : 'threat-nominal';

  return (
    <div className={`eval-header ${superBreachMode ? 'super-breach-header' : ''}`}>
      <div className="eval-header-inner">
        {/* Left section */}
        <div className="flex items-center gap-6">
          {/* Breach status */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${superBreachMode ? 'bg-matrix-red' : 'bg-matrix-bright'} animate-pulse`} />
            <GlitchText
              text={superBreachMode ? "CHEAT MODE ACTIVE" : "NEURAL BREACH ACTIVE"}
              glitchProbability={superBreachMode ? 0.15 : 0.03}
            />
          </div>

          {/* Threat level */}
          <div className="flex items-center gap-2">
            <Shield className="w-3.5 h-3.5" />
            <span className="text-matrix-dim">threat.level:</span>
            <span className={threatClass}>
              <GlitchText text={threatLevel} glitchProbability={threatLevel === 'CRITICAL' ? 0.1 : 0.02} />
            </span>
          </div>
        </div>

        {/* Center section - hidden message area */}
        <div className="flex-1 flex justify-center items-center min-w-[200px]">
          {hiddenMessage && (
            <span className="hidden-message text-matrix-dim text-xs font-mono animate-flicker">
              {hiddenMessage}
            </span>
          )}
        </div>

        {/* Right section */}
        <div className="flex items-center gap-6">
          {/* Uptime */}
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5 text-matrix-dim" />
            <span className="text-matrix-dim">UPTIME:</span>
            <span className="text-matrix-bright font-mono tabular-nums">
              {formatUptime(uptime)}
            </span>
          </div>

          {/* Agents status */}
          <div className="flex items-center gap-2">
            <Radio className="w-3.5 h-3.5 text-matrix-dim" />
            <span className="text-matrix-dim">AGENTS:</span>
            <span className="text-matrix-bright font-mono">
              {activeAgentCount}/{agents.filter(a => !a.isVirtual).length}
            </span>
            <span className="text-matrix-neon text-xs">LIVE</span>
          </div>

          {/* Cycles counter */}
          <div className="flex items-center gap-2">
            <Zap className="w-3.5 h-3.5 text-matrix-amber" />
            <span className="text-matrix-dim">CYCLES:</span>
            <span className="text-matrix-amber font-mono tabular-nums">
              {formatCycles(cycles)}
            </span>
          </div>

          {/* Intercept status */}
          <div className="flex items-center gap-2">
            <Skull className="w-3.5 h-3.5 text-matrix-red" />
            <span className="text-matrix-dim">INTERCEPT:</span>
            <span className="text-matrix-neon">ACTIVE</span>
          </div>
        </div>
      </div>
    </div>
  );
}
