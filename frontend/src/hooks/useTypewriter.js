import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * useTypewriter - ChatGPT-style character streaming animation
 *
 * Features:
 * - Character-level streaming (2-5 chars per batch)
 * - Variable pacing with punctuation pauses
 * - Smooth acceleration curve (starts slower, speeds up)
 * - Natural, fluid text reveal like ChatGPT/Claude
 *
 * @param {string} targetText - The full text to reveal
 * @param {Object} options - Configuration options
 * @param {number} options.speed - Speed multiplier (1.0 = normal, 2.0 = 2x faster)
 * @param {boolean} options.isActive - Whether streaming is active
 * @param {boolean} options.alwaysAnimate - Force animation even on preloaded content
 * @returns {{ displayText: string, isTyping: boolean }}
 */
const useTypewriter = (targetText, { speed = 1.0, isActive = true, alwaysAnimate = false } = {}) => {
  const [displayText, setDisplayText] = useState('');
  const [isTyping, setIsTyping] = useState(false);

  // Refs for mutable state
  const revealedIndexRef = useRef(0);
  const timeoutRef = useRef(null);
  const totalRevealedRef = useRef(0); // For acceleration curve
  const targetTextRef = useRef(targetText);
  const isActiveRef = useRef(isActive);
  const speedRef = useRef(speed);
  const initialLoadRef = useRef(true);
  const wasPreloadedRef = useRef(!alwaysAnimate && !isActive && !!targetText);
  const hasEverBeenActiveRef = useRef(alwaysAnimate || isActive);
  const alwaysAnimateRef = useRef(alwaysAnimate);
  const isRunningRef = useRef(false);

  // Keep refs in sync
  useEffect(() => {
    targetTextRef.current = targetText;
  }, [targetText]);

  useEffect(() => {
    isActiveRef.current = isActive;
    if (isActive) {
      hasEverBeenActiveRef.current = true;
    }
  }, [isActive]);

  useEffect(() => {
    speedRef.current = speed;
  }, [speed]);

  /**
   * Calculate delay for the next batch based on the last character revealed
   * - Punctuation gets longer pauses for natural reading
   * - Acceleration curve makes text speed up over time
   */
  const getDelay = useCallback((lastChar) => {
    const baseDelay = 18; // Base delay in ms
    let delay = baseDelay;

    // Punctuation pauses for natural rhythm
    if (/[.!?]/.test(lastChar)) {
      delay += 45; // End of sentence - longer pause
    } else if (/[,;:]/.test(lastChar)) {
      delay += 20; // Mid-sentence punctuation
    } else if (lastChar === '\n') {
      delay += 35; // Newline pause
    }

    // Acceleration curve: start at 0.7x, ramp to 1.2x over first 80 chars
    const progress = Math.min(totalRevealedRef.current / 80, 1);
    const accelFactor = 0.7 + (progress * 0.5); // 0.7 → 1.2

    // Apply acceleration and speed multiplier
    return Math.max(8, delay / accelFactor / speedRef.current);
  }, []);

  /**
   * Determine batch size based on upcoming characters
   * - Smaller batches near punctuation (dramatic effect)
   * - Larger batches for spaces/regular text (flow)
   */
  const getBatchSize = useCallback(() => {
    const current = revealedIndexRef.current;
    const text = targetTextRef.current || '';
    const upcoming = text.slice(current, current + 5);

    if (!upcoming) return 1;

    // Single char for punctuation (creates pause effect)
    if (/^[.!?]/.test(upcoming)) return 1;
    if (/^[,;:\n]/.test(upcoming)) return 1;

    // Larger batches for spaces (faster through whitespace)
    if (/^\s/.test(upcoming)) {
      return 3 + Math.floor(Math.random() * 2); // 3-4 chars
    }

    // Default: 2-3 chars for regular text
    return 2 + Math.floor(Math.random() * 2);
  }, []);

  /**
   * Main reveal loop - recursive setTimeout for precise timing
   */
  const revealNext = useCallback(() => {
    const current = revealedIndexRef.current;
    const target = targetTextRef.current?.length || 0;

    // Check if we've caught up with all available text
    if (current >= target) {
      setDisplayText(targetTextRef.current || '');

      // If streaming ended and we're caught up, stop
      if (!isActiveRef.current) {
        setIsTyping(false);
        isRunningRef.current = false;
        return;
      }

      // Still streaming - wait for more content
      setIsTyping(false);
      timeoutRef.current = setTimeout(revealNext, 40);
      return;
    }

    // Reveal next batch of characters
    const batchSize = getBatchSize();
    const nextIndex = Math.min(current + batchSize, target);
    const lastChar = targetTextRef.current[nextIndex - 1] || '';

    // Update state
    revealedIndexRef.current = nextIndex;
    totalRevealedRef.current += (nextIndex - current);
    setDisplayText(targetTextRef.current.slice(0, nextIndex));
    setIsTyping(true);

    // Schedule next reveal with variable delay
    const delay = getDelay(lastChar);
    timeoutRef.current = setTimeout(revealNext, delay);
  }, [getBatchSize, getDelay]);

  /**
   * Start the reveal animation
   */
  const startReveal = useCallback(() => {
    if (isRunningRef.current) return;
    isRunningRef.current = true;
    revealNext();
  }, [revealNext]);

  /**
   * Stop the reveal animation
   */
  const stopReveal = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    isRunningRef.current = false;
  }, []);

  // Handle text arriving and animation start
  useEffect(() => {
    // Check instant display conditions
    const shouldDisplayInstantly = wasPreloadedRef.current ||
      (!alwaysAnimateRef.current && initialLoadRef.current && targetText && !isActive) ||
      (targetText && !hasEverBeenActiveRef.current);

    if (shouldDisplayInstantly) {
      revealedIndexRef.current = targetText?.length || 0;
      totalRevealedRef.current = targetText?.length || 0;
      setDisplayText(targetText || '');
      setIsTyping(false);
      initialLoadRef.current = false;
      return;
    }
    initialLoadRef.current = false;

    // Start animation if we have text to reveal
    if (targetText && revealedIndexRef.current < targetText.length) {
      startReveal();
    }
  }, [targetText, isActive, startReveal]);

  // Handle text being cleared
  useEffect(() => {
    if (!targetText) {
      stopReveal();
      revealedIndexRef.current = 0;
      totalRevealedRef.current = 0;
      setDisplayText('');
      setIsTyping(false);
    }
  }, [targetText, stopReveal]);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopReveal();
  }, [stopReveal]);

  return { displayText, isTyping };
};

export default useTypewriter;
