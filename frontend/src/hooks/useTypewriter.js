import { useState, useEffect, useRef } from 'react';

/**
 * useTypewriter - Word-by-word text reveal animation
 *
 * Buffers incoming text and reveals it word-by-word at a specified speed.
 * When streaming ends, typewriter continues until caught up (smooth finish).
 *
 * @param {string} targetText - The full text to reveal
 * @param {Object} options - Configuration options
 * @param {number} options.speed - Characters per second (default: 50)
 * @param {boolean} options.isActive - Whether streaming is active (default: true)
 * @returns {{ displayText: string, isTyping: boolean }}
 */
const useTypewriter = (targetText, { speed = 50, isActive = true } = {}) => {
  const [displayText, setDisplayText] = useState('');
  const [isTyping, setIsTyping] = useState(false);

  // Refs for mutable state that persists across renders
  const revealedIndexRef = useRef(0);
  const intervalRef = useRef(null);
  const targetTextRef = useRef(targetText);
  const isActiveRef = useRef(isActive);
  const initialLoadRef = useRef(true);  // Track if this is initial render
  // Track if text was preloaded (existed on first render with isActive=false)
  const wasPreloadedRef = useRef(!isActive && !!targetText);
  // Track if streaming has ever been active
  const hasEverBeenActiveRef = useRef(isActive);

  // Keep refs in sync
  useEffect(() => {
    targetTextRef.current = targetText;
  }, [targetText]);

  useEffect(() => {
    isActiveRef.current = isActive;
    // Track if streaming has ever started
    if (isActive) {
      hasEverBeenActiveRef.current = true;
    }
  }, [isActive]);

  // Find the next word boundary from current position
  const findNextWordEnd = (text, startIndex) => {
    if (startIndex >= text.length) return text.length;

    let pos = startIndex;
    // Skip whitespace
    while (pos < text.length && /\s/.test(text[pos])) {
      pos++;
    }
    // Find end of word
    while (pos < text.length && !/\s/.test(text[pos])) {
      pos++;
    }
    return pos;
  };

  // Start the interval (called once)
  const startInterval = () => {
    if (intervalRef.current) return; // Already running

    const intervalMs = Math.max(20, (5 / speed) * 1000);

    intervalRef.current = setInterval(() => {
      const currentTarget = targetTextRef.current || '';
      const currentRevealed = revealedIndexRef.current;

      if (currentRevealed < currentTarget.length) {
        // Reveal next word
        const nextWordEnd = findNextWordEnd(currentTarget, currentRevealed);
        revealedIndexRef.current = nextWordEnd;
        setDisplayText(currentTarget.slice(0, nextWordEnd));
        setIsTyping(true);
      } else {
        // Caught up with all text
        setDisplayText(currentTarget);

        // If streaming ended AND we've caught up, stop the interval
        if (!isActiveRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
          setIsTyping(false);
        } else {
          // Still streaming, keep interval alive for new text
          setIsTyping(false);
        }
      }
    }, intervalMs);
  };

  // Stop the interval
  const stopInterval = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  // Handle text arriving - start interval if needed
  // Start interval if we have text to reveal (whether streaming or not)
  useEffect(() => {
    // INSTANT DISPLAY CONDITIONS:
    // 1. Text was preloaded (existed on mount with isActive=false), OR
    // 2. Initial load with text but streaming not active, OR
    // 3. We have text but streaming was NEVER active
    const shouldDisplayInstantly = wasPreloadedRef.current ||
                                   (initialLoadRef.current && targetText && !isActive) ||
                                   (targetText && !hasEverBeenActiveRef.current);

    if (shouldDisplayInstantly) {
      revealedIndexRef.current = targetText?.length || 0;
      setDisplayText(targetText || '');
      setIsTyping(false);
      initialLoadRef.current = false;
      return;
    }
    initialLoadRef.current = false;

    // Otherwise, animate word-by-word
    if (targetText && !intervalRef.current && revealedIndexRef.current < targetText.length) {
      startInterval();
    }
  }, [targetText, isActive, speed]);

  // Handle text being cleared
  useEffect(() => {
    if (!targetText) {
      stopInterval();
      revealedIndexRef.current = 0;
      setDisplayText('');
      setIsTyping(false);
    }
  }, [targetText]);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopInterval();
  }, []);

  return { displayText, isTyping };
};

export default useTypewriter;
