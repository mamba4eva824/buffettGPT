import { useState, useCallback, useRef } from 'react';

/**
 * Tracks a custom history stack of visited app modes,
 * enabling back/forward navigation without touching browser history.
 */
export function useModeHistory(initialMode) {
  const [state, setState] = useState({ history: [initialMode], index: 0 });
  const isHistoryNavRef = useRef(false);

  const canGoBack = state.index > 0;
  const canGoForward = state.index < state.history.length - 1;

  const navigateToMode = useCallback((newMode) => {
    isHistoryNavRef.current = false;
    setState(prev => {
      // Deduplicate consecutive same-mode entries
      if (prev.history[prev.index] === newMode) return prev;
      // Truncate forward history and push new mode
      const truncated = prev.history.slice(0, prev.index + 1);
      return { history: [...truncated, newMode], index: truncated.length };
    });
  }, []);

  const goBack = useCallback(() => {
    let targetMode = null;
    isHistoryNavRef.current = true;
    setState(prev => {
      if (prev.index <= 0) return prev;
      const newIndex = prev.index - 1;
      targetMode = prev.history[newIndex];
      return { ...prev, index: newIndex };
    });
    return targetMode;
  }, []);

  const goForward = useCallback(() => {
    let targetMode = null;
    isHistoryNavRef.current = true;
    setState(prev => {
      if (prev.index >= prev.history.length - 1) return prev;
      const newIndex = prev.index + 1;
      targetMode = prev.history[newIndex];
      return { ...prev, index: newIndex };
    });
    return targetMode;
  }, []);

  return {
    navigateToMode,
    goBack,
    goForward,
    canGoBack,
    canGoForward,
    isHistoryNavRef,
  };
}
