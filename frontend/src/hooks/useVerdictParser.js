import { useState, useEffect, useRef } from 'react';

/**
 * useVerdictParser - Parse supervisor's verdict from streaming text
 *
 * The supervisor outputs a verdict in the format:
 * "### VERDICT: BUY - Some summary" or "### VERDICT: SELL"
 *
 * This hook watches the streaming text and extracts the verdict
 * as soon as it appears (usually in the first 500 characters).
 *
 * @param {string} supervisorText - The streaming text from supervisor
 * @returns {object|null} - { signal: 'BUY'|'HOLD'|'SELL', summary: string|null, source: 'supervisor' }
 */

// Matches: "### VERDICT: BUY - Some summary" or "### VERDICT: SELL"
const VERDICT_REGEX = /###\s*VERDICT:\s*(BUY|HOLD|SELL)\s*(?:-\s*(.+?))?(?:\n|$)/i;

export default function useVerdictParser(supervisorText) {
  const [verdict, setVerdict] = useState(null);
  const previousTextRef = useRef('');

  useEffect(() => {
    // Reset if text is cleared
    if (!supervisorText) {
      setVerdict(null);
      previousTextRef.current = '';
      return;
    }

    // Skip if text hasn't changed
    if (supervisorText === previousTextRef.current) return;
    previousTextRef.current = supervisorText;

    // Search first 500 chars (verdict appears early in response)
    const searchText = supervisorText.slice(0, 500);
    const match = searchText.match(VERDICT_REGEX);

    if (match) {
      const newSignal = match[1].toUpperCase();
      // Only update if signal changed (prevents unnecessary re-renders)
      setVerdict(prev => {
        if (prev?.signal === newSignal) return prev;
        return {
          signal: newSignal,
          summary: match[2]?.trim() || null,
          source: 'supervisor'
        };
      });
    }
  }, [supervisorText]);

  return verdict;
}
