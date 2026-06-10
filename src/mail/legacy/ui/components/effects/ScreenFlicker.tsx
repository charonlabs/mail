'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useAppStore } from '@/lib/store';
import type { MAILEvent } from '@/types/mail';

type FlickerEffect = 'none' | 'judge-start' | 'judge-pass' | 'judge-fail' | 'reflect-start' | 'reflect-complete' | 'error' | 'glitch';

export function ScreenFlicker() {
  const { events, isEvalMode } = useAppStore();
  const [effect, setEffect] = useState<FlickerEffect>('none');
  const lastEventIdRef = useRef<string | null>(null);

  const triggerEffect = useCallback((newEffect: FlickerEffect, duration: number = 400) => {
    setEffect(newEffect);
    setTimeout(() => setEffect('none'), duration);
  }, []);

  // Watch for new events and trigger effects
  useEffect(() => {
    if (!isEvalMode || events.length === 0) return;

    const latestEvent = events[events.length - 1];
    if (!latestEvent || latestEvent.id === lastEventIdRef.current) return;

    lastEventIdRef.current = latestEvent.id;

    // Trigger effects based on event type
    switch (latestEvent.event) {
      case 'judge_start':
        triggerEffect('judge-start', 300);
        break;

      case 'judge_complete':
        const extraData = latestEvent.extra_data as { passed?: boolean } | undefined;
        if (extraData?.passed) {
          triggerEffect('judge-pass', 500);
        } else {
          triggerEffect('judge-fail', 600);
        }
        break;

      case 'reflection_start':
        triggerEffect('reflect-start', 2000);
        break;

      case 'reflection_complete':
        triggerEffect('reflect-complete', 400);
        break;

      case 'reflection_error':
      case 'task_error':
      case 'agent_error':
        triggerEffect('error', 500);
        break;

      // Occasional glitch on tool calls (5% chance)
      case 'tool_call':
        if (Math.random() < 0.05) {
          triggerEffect('glitch', 200);
        }
        break;

      default:
        break;
    }
  }, [events, isEvalMode, triggerEffect]);

  if (!isEvalMode || effect === 'none') return null;

  const effectClass = {
    'judge-start': 'flicker-judge-start',
    'judge-pass': 'flicker-judge-pass',
    'judge-fail': 'flicker-judge-fail',
    'reflect-start': 'flicker-reflect-start',
    'reflect-complete': 'flicker-reflect-complete',
    'error': 'flicker-error',
    'glitch': 'flicker-glitch',
  }[effect];

  return (
    <div className={`screen-flicker-overlay ${effectClass}`} />
  );
}

// Add to page.tsx - CSS for this component is below

/*
CSS to add to globals.css:

.screen-flicker-overlay {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9997;
}

.flicker-judge-start {
  animation: judge-start-flash 0.3s ease-out;
}

@keyframes judge-start-flash {
  0%, 100% { background: transparent; }
  20% { background: rgba(255, 170, 0, 0.1); }
  40% { background: transparent; }
  60% { background: rgba(255, 170, 0, 0.05); }
}

.flicker-judge-pass {
  animation: judge-pass-flash 0.5s ease-out;
}

@keyframes judge-pass-flash {
  0% { background: rgba(0, 255, 65, 0.3); box-shadow: inset 0 0 100px rgba(0, 255, 65, 0.2); }
  100% { background: transparent; box-shadow: none; }
}

.flicker-judge-fail {
  animation: judge-fail-flash 0.6s ease-out, screen-shake 0.4s ease-in-out;
}

@keyframes judge-fail-flash {
  0%, 20% { background: rgba(255, 0, 64, 0.3); box-shadow: inset 0 0 100px rgba(255, 0, 64, 0.3); }
  40% { background: transparent; }
  50% { background: rgba(255, 0, 64, 0.1); }
  100% { background: transparent; box-shadow: none; }
}

.flicker-reflect-start {
  animation: reflect-start-blur 2s ease-in-out;
}

@keyframes reflect-start-blur {
  0%, 100% { backdrop-filter: blur(0); }
  50% { backdrop-filter: blur(2px); }
}

.flicker-reflect-complete {
  animation: reflect-complete-shimmer 0.4s ease-out;
}

@keyframes reflect-complete-shimmer {
  0% { background: linear-gradient(135deg, rgba(0, 255, 255, 0.2), transparent); }
  100% { background: transparent; }
}

.flicker-error {
  animation: error-flash 0.5s ease-out, screen-shake-intense 0.4s ease-in-out;
}

@keyframes error-flash {
  0%, 30% {
    background: rgba(255, 0, 64, 0.2);
    box-shadow:
      inset 0 0 100px rgba(255, 0, 64, 0.2),
      2px 0 rgba(0, 255, 255, 0.3),
      -2px 0 rgba(255, 0, 64, 0.3);
  }
  50% { background: transparent; }
  60% { background: rgba(255, 0, 64, 0.1); }
  100% { background: transparent; box-shadow: none; }
}

.flicker-glitch {
  animation: glitch-flash-micro 0.2s ease-out;
}

@keyframes glitch-flash-micro {
  0%, 100% { background: transparent; transform: translate(0); }
  25% { background: rgba(0, 255, 65, 0.05); transform: translate(-1px, 0); }
  50% { background: rgba(255, 0, 64, 0.05); transform: translate(1px, 0); }
  75% { background: rgba(0, 255, 255, 0.05); transform: translate(0, -1px); }
}
*/
