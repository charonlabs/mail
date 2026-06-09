'use client';

import { useEffect, useRef, useMemo } from 'react';
import { useAppStore } from '@/lib/store';

// Katakana, numbers, symbols for the rain
const MATRIX_CHARS = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ@#$%&*+=<>?';

// Words that can form in the rain
const SPECIAL_WORDS = ['MAIL', 'EVAL', 'JUDGE', 'REFLECT', 'BREACH', 'NEURAL', 'SYSTEM'];
const EASTER_EGG_WORD = 'HELLO RYAN'; // Super rare!

interface Column {
  x: number;
  y: number;
  speed: number;
  chars: string[];
  opacity: number;
  specialWord?: string;
  specialIndex?: number;
}

export function MatrixRain() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const columnsRef = useRef<Column[]>([]);
  const animationRef = useRef<number | null>(null);
  const { events, agents } = useAppStore();

  // Check if agents are actively doing things
  const isActive = useMemo(() => {
    const recentEvents = events.slice(-10);
    return recentEvents.some(e =>
      e.event === 'tool_call' || e.event === 'new_message' || e.event === 'judge_start'
    );
  }, [events]);

  // Get agent names for potential word formation
  const agentNames = useMemo(() =>
    agents.filter(a => !a.isVirtual).map(a => a.name.toUpperCase()),
    [agents]
  );

  // Use refs so the animation loop can read current values without re-running the effect
  const isActiveRef = useRef(isActive);
  const agentNamesRef = useRef(agentNames);

  // Update refs when values change (doesn't cause effect re-run)
  useEffect(() => {
    isActiveRef.current = isActive;
  }, [isActive]);

  useEffect(() => {
    agentNamesRef.current = agentNames;
  }, [agentNames]);

  // Main effect - only runs once on mount
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      initColumns();
    };

    const initColumns = () => {
      const fontSize = 14;
      const columnCount = Math.floor(canvas.width / fontSize);
      columnsRef.current = [];

      for (let i = 0; i < columnCount; i++) {
        // Only create columns for ~30% of positions (sparse rain)
        if (Math.random() < 0.3) {
          columnsRef.current.push({
            x: i * fontSize,
            y: Math.random() * canvas.height,
            speed: 0.5 + Math.random() * 1.5, // Base speed
            chars: Array.from({ length: 20 }, () =>
              MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)]
            ),
            opacity: 0.1 + Math.random() * 0.2, // Very subtle
          });
        }
      }
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Animation loop
    const animate = () => {
      if (!ctx || !canvas) return;

      // Semi-transparent black to create trail effect
      ctx.fillStyle = 'rgba(3, 5, 3, 0.05)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const fontSize = 14;
      ctx.font = `${fontSize}px "JetBrains Mono", monospace`;

      columnsRef.current.forEach((column) => {
        // Speed boost when active - read from ref
        const speedMultiplier = isActiveRef.current ? 1.5 : 1;
        column.y += column.speed * speedMultiplier;

        // Draw each character in the column
        column.chars.forEach((char, charIndex) => {
          const charY = column.y - charIndex * fontSize;

          // Skip if off screen
          if (charY < 0 || charY > canvas.height) return;

          // Calculate opacity based on position (fade trail)
          const fadeOpacity = column.opacity * (1 - charIndex / column.chars.length);

          // First character is brighter (the "head")
          if (charIndex === 0) {
            ctx.fillStyle = `rgba(57, 255, 20, ${column.opacity * 1.5})`;
            ctx.shadowColor = '#39ff14';
            ctx.shadowBlur = 1; // Minimal glow for crisp letters
          } else {
            ctx.fillStyle = `rgba(0, 255, 65, ${fadeOpacity})`;
            ctx.shadowBlur = 0;
          }

          ctx.fillText(char, column.x, charY);
        });

        // Reset shadow
        ctx.shadowBlur = 0;

        // Reset column when it goes off screen
        if (column.y - column.chars.length * fontSize > canvas.height) {
          column.y = 0;
          column.speed = 0.5 + Math.random() * 1.5;

          // Small chance to assign a special word
          if (Math.random() < 0.001) { // 0.1% chance
            // Even smaller chance for easter egg
            if (Math.random() < 0.01) { // 0.01% overall
              column.specialWord = EASTER_EGG_WORD;
            } else {
              // Pick from agent names or special words - read from ref
              const allWords = [...SPECIAL_WORDS, ...agentNamesRef.current];
              column.specialWord = allWords[Math.floor(Math.random() * allWords.length)];
            }
            column.specialIndex = 0;
          } else {
            column.specialWord = undefined;
          }

          // Regenerate characters
          column.chars = Array.from({ length: 20 }, (_, i) => {
            if (column.specialWord && i < column.specialWord.length) {
              return column.specialWord[i];
            }
            return MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
          });
        }

        // Occasionally mutate a random character (makes it feel alive)
        if (Math.random() < 0.02) {
          const mutateIndex = Math.floor(Math.random() * column.chars.length);
          if (!column.specialWord || mutateIndex >= column.specialWord.length) {
            column.chars[mutateIndex] = MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
          }
        }
      });

      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, []); // Empty dependency array - only runs once

  return (
    <canvas
      ref={canvasRef}
      className="matrix-rain"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 1,
        opacity: 0.4, // Keep it subtle
      }}
    />
  );
}
