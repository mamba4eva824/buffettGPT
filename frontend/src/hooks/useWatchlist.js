import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchWatchlist, addToWatchlist, removeFromWatchlist } from '../api/watchlistApi';

export default function useWatchlist(token) {
  const [watchlistData, setWatchlistData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  const refresh = useCallback(async () => {
    if (!token) return;

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const result = await fetchWatchlist(token);
      if (controller.signal.aborted) return;
      setWatchlistData(result);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err.message || 'Failed to fetch watchlist');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    refresh();
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, [refresh]);

  const addTicker = useCallback(async (ticker) => {
    if (!token) return;
    try {
      await addToWatchlist(ticker, token);
      await refresh();
    } catch (err) {
      setError(err.message || `Failed to add ${ticker}`);
      throw err;
    }
  }, [token, refresh]);

  const removeTicker = useCallback(async (ticker) => {
    if (!token) return;
    // Optimistic removal from local state
    setWatchlistData(prev => {
      if (!prev || !prev.watchlist) return prev;
      return { ...prev, watchlist: prev.watchlist.filter(item => item.ticker !== ticker) };
    });
    try {
      await removeFromWatchlist(ticker, token);
    } catch (err) {
      setError(err.message || `Failed to remove ${ticker}`);
      await refresh(); // Revert on failure
      throw err;
    }
  }, [token, refresh]);

  return { watchlistData, loading, error, addTicker, removeTicker, refresh };
}
