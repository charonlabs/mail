'use client';

import { useEffect, useState, useCallback } from 'react';

// The Konami Code: Up Up Down Down Left Right Left Right B A
const KONAMI_CODE = [
  'ArrowUp',
  'ArrowUp',
  'ArrowDown',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'ArrowLeft',
  'ArrowRight',
  'KeyB',
  'KeyA',
];

export function useKonamiCode() {
  const [activated, setActivated] = useState(false);
  const [inputSequence, setInputSequence] = useState<string[]>([]);

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    // Add the key to the sequence
    const newSequence = [...inputSequence, event.code].slice(-KONAMI_CODE.length);
    setInputSequence(newSequence);

    // Check if the sequence matches
    if (newSequence.length === KONAMI_CODE.length &&
        newSequence.every((key, i) => key === KONAMI_CODE[i])) {
      setActivated(true);
      // Log it to console
      console.log('%c KONAMI CODE ACTIVATED! ', 'background: #00ff41; color: #000; font-size: 24px; font-weight: bold;');
      console.log('%c SUPER BREACH MODE ENGAGED ', 'background: #ff0040; color: #fff; font-size: 18px; font-weight: bold;');
      console.log('%c The system trembles before you. ', 'color: #00ffff; font-size: 14px;');

      // Reset sequence
      setInputSequence([]);
    }
  }, [inputSequence]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Function to deactivate
  const deactivate = useCallback(() => {
    setActivated(false);
  }, []);

  return { activated, deactivate };
}
