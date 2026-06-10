'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

interface BreachSequenceProps {
  onComplete: () => void;
}

// ASCII skull for easter egg (appears for 100ms)
const SKULL_ASCII = `
    ███████
   ██     ██
  ██  ███  ██
  ██ █████ ██
  ██  ███  ██
   ██     ██
    ███████
      ███
   ████ ████
`;

type Stage = 'boot' | 'hacking' | 'alert' | 'glitch' | 'access' | 'skull' | 'fadeout';

interface TerminalLine {
  text: string;
  type: 'command' | 'output' | 'progress' | 'alert' | 'success' | 'warning';
  delay?: number; // ms before showing this line
}

const BOOT_LINES: TerminalLine[] = [
  { text: 'MAIL NEURAL INTERFACE v4.5.1', type: 'output', delay: 0 },
  { text: '', type: 'output', delay: 200 },
  { text: '> Initializing covert tunnel...', type: 'command', delay: 400 },
  { text: '> Target acquired: [EVAL_SERVER:8001]', type: 'command', delay: 800 },
  { text: '> Spoofing authentication tokens...', type: 'command', delay: 1200 },
  { text: 'PROGRESS:70', type: 'progress', delay: 1600 },
  { text: '> Bypassing firewall...', type: 'command', delay: 2800 },
  { text: '> Firewall detected. Deploying neural exploit...', type: 'warning', delay: 3200 },
];

const ALERT_LINES: TerminalLine[] = [
  { text: '', type: 'output', delay: 0 },
  { text: '  ALERT: INTRUSION DETECTED IN SECTOR 7G', type: 'alert', delay: 200 },
  { text: '  INITIATING COUNTERMEASURES...', type: 'alert', delay: 600 },
  { text: '', type: 'output', delay: 1000 },
  { text: '> Countermeasures neutralized.', type: 'success', delay: 1400 },
  { text: '> Injecting payload into neural subnet...', type: 'command', delay: 1800 },
  { text: 'PROGRESS:100', type: 'progress', delay: 2200 },
];

function TypedText({ text, speed = 30, onComplete }: { text: string; speed?: number; onComplete?: () => void }) {
  const [displayed, setDisplayed] = useState('');
  const [cursorVisible, setCursorVisible] = useState(true);

  useEffect(() => {
    if (displayed.length < text.length) {
      const timeout = setTimeout(() => {
        setDisplayed(text.slice(0, displayed.length + 1));
      }, speed + Math.random() * 20); // Slight randomness for realism
      return () => clearTimeout(timeout);
    } else if (onComplete) {
      onComplete();
    }
  }, [displayed, text, speed, onComplete]);

  // Blinking cursor
  useEffect(() => {
    const interval = setInterval(() => {
      setCursorVisible(v => !v);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  return (
    <span>
      {displayed}
      {displayed.length < text.length && (
        <span className={`cursor ${cursorVisible ? 'opacity-100' : 'opacity-0'}`}>_</span>
      )}
    </span>
  );
}

function ProgressBar({ targetPercent, duration = 1200 }: { targetPercent: number; duration?: number }) {
  const [percent, setPercent] = useState(0);

  useEffect(() => {
    const startTime = Date.now();
    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      setPercent(Math.floor(progress * targetPercent));

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };
    requestAnimationFrame(animate);
  }, [targetPercent, duration]);

  const filled = Math.floor(percent / 5);
  const empty = 20 - filled;

  return (
    <span className="font-mono">
      [{'\u2588'.repeat(filled)}{'\u2591'.repeat(empty)}] {percent}%
    </span>
  );
}

export function BreachSequence({ onComplete }: BreachSequenceProps) {
  const [stage, setStage] = useState<Stage>('boot');
  const [visibleLines, setVisibleLines] = useState<number>(0);
  const [currentLines, setCurrentLines] = useState<TerminalLine[]>(BOOT_LINES);
  const [progressTarget, setProgressTarget] = useState(70);
  const [showSkull, setShowSkull] = useState(false);
  const skullClickedRef = useRef(false);
  const skipRef = useRef(false);

  const skipToAccess = useCallback(() => {
    skipRef.current = true;
    setShowSkull(false);
    setStage((current) => (current === 'access' || current === 'fadeout' ? current : 'access'));
  }, []);

  // Allow skipping to ACCESS GRANTED with Esc
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        skipToAccess();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [skipToAccess]);

  // Progress through boot lines
  useEffect(() => {
    if (stage === 'boot' && visibleLines < BOOT_LINES.length) {
      const nextLine = BOOT_LINES[visibleLines];
      const delay = nextLine?.delay || 200;
      const timeout = setTimeout(() => {
        setVisibleLines(v => v + 1);
      }, delay);
      return () => clearTimeout(timeout);
    } else if (stage === 'boot' && visibleLines >= BOOT_LINES.length) {
      // Move to alert stage
      setTimeout(() => {
        if (skipRef.current) return;
        setStage('alert');
        setCurrentLines(ALERT_LINES);
        setVisibleLines(0);
        setProgressTarget(100);
      }, 800);
    }
  }, [stage, visibleLines]);

  // Progress through alert lines
  useEffect(() => {
    if (stage === 'alert' && visibleLines < ALERT_LINES.length) {
      const nextLine = ALERT_LINES[visibleLines];
      const delay = nextLine?.delay || 200;
      const timeout = setTimeout(() => {
        setVisibleLines(v => v + 1);
      }, delay);
      return () => clearTimeout(timeout);
    } else if (stage === 'alert' && visibleLines >= ALERT_LINES.length) {
      // Move to glitch stage
      setTimeout(() => {
        if (skipRef.current) return;
        setStage('glitch');
      }, 600);
    }
  }, [stage, visibleLines]);

  // Glitch effect then access granted
  useEffect(() => {
    if (stage === 'glitch') {
      // Brief intense glitch
      setTimeout(() => {
        if (skipRef.current) return;
        // 10% chance to show skull
        if (Math.random() < 0.1) {
          setStage('skull');
          setShowSkull(true);
          // Skull only shows for 150ms
          setTimeout(() => {
            if (skipRef.current) return;
            setShowSkull(false);
            setStage('access');
          }, 150);
        } else {
          setStage('access');
        }
      }, 300);
    }
  }, [stage]);

  // Access granted then complete
  useEffect(() => {
    if (stage === 'access') {
      setTimeout(() => {
        setStage('fadeout');
      }, 2000);
    }
  }, [stage]);

  // Fadeout then complete
  useEffect(() => {
    if (stage === 'fadeout') {
      setTimeout(() => {
        onComplete();
      }, 500);
    }
  }, [stage, onComplete]);

  // Handle skull click easter egg
  const handleSkullClick = useCallback(() => {
    if (!skullClickedRef.current) {
      skullClickedRef.current = true;
      console.log('%c YOU FOUND THE SKULL! ', 'background: #ff0040; color: #fff; font-size: 20px; font-weight: bold;');
      console.log('%c The system knows you are here. ', 'color: #00ff41; font-size: 14px;');
      console.log('%c Welcome to the neural breach, Ryan. ', 'color: #00ffff; font-size: 14px;');
    }
  }, []);

  const renderLine = (line: TerminalLine, index: number) => {
    if (line.type === 'progress') {
      return (
        <div key={index} className="terminal-line text-matrix-bright">
          {'  '}
          <ProgressBar targetPercent={progressTarget} />
        </div>
      );
    }

    const colorClass = {
      command: 'text-matrix-bright',
      output: 'text-matrix-dim',
      alert: 'text-matrix-red breach-alert',
      success: 'text-matrix-neon',
      warning: 'text-matrix-amber',
      progress: 'text-matrix-bright',
    }[line.type];

    return (
      <div key={index} className={`terminal-line ${colorClass}`}>
        {line.type === 'alert' ? (
          <span className="font-bold animate-pulse">{line.text}</span>
        ) : (
          line.text
        )}
      </div>
    );
  };

  return (
    <div className={`breach-overlay ${stage === 'fadeout' ? 'opacity-0' : 'opacity-100'} transition-opacity duration-500`}>
      {/* Scanlines overlay */}
      <div className="breach-scanlines" />

      {/* Screen shake during glitch */}
      <div className={`breach-content ${stage === 'glitch' ? 'screen-shake-intense' : ''}`}>
        {/* Terminal output - Boot and Alert stages */}
        {(stage === 'boot' || stage === 'alert') && (
          <div className="breach-terminal">
            <div className="terminal-window">
              {/* Render previous boot lines when in alert stage */}
              {stage === 'alert' && BOOT_LINES.map((line, i) => renderLine(line, i))}

              {/* Render current stage lines */}
              {currentLines.slice(0, visibleLines).map((line, i) =>
                renderLine(line, stage === 'alert' ? BOOT_LINES.length + i : i)
              )}

              {/* Cursor at end */}
              <div className="terminal-line text-matrix-bright">
                <span className="animate-pulse">_</span>
              </div>
            </div>
          </div>
        )}

        {/* Glitch flash */}
        {stage === 'glitch' && (
          <div className="glitch-flash" />
        )}

        {/* Skull easter egg */}
        {stage === 'skull' && showSkull && (
          <div
            className="skull-container cursor-pointer"
            onClick={handleSkullClick}
          >
            <pre className="text-matrix-red text-xs leading-none animate-pulse">
              {SKULL_ASCII}
            </pre>
          </div>
        )}

        {/* ACCESS GRANTED */}
        {stage === 'access' && (
          <div className="breach-access-granted">
            <div className="access-box">
              <div className="access-border" />
              <div className="access-text">
                <span className="access-main">ACCESS</span>
                <span className="access-sub">G R A N T E D</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Version number in corner */}
      <div className="absolute bottom-4 right-4 text-matrix-dim text-xs font-mono opacity-50">
        MAIL://BREACH v1.0.0
      </div>
    </div>
  );
}
