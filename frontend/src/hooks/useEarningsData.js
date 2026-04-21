import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchRecentEarnings, fetchUpcomingEarnings, fetchSeasonOverview } from '../api/earningsApi';

export default function useEarningsData(activeTab) {
  const [recentData, setRecentData] = useState(null);
  const [upcomingData, setUpcomingData] = useState(null);
  const [seasonData, setSeasonData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const abortRef = useRef(null);

  // Upcoming pagination state
  const [upcomingCursor, setUpcomingCursor] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    let fetcher;
    if (activeTab === 'recent') {
      fetcher = fetchRecentEarnings();
    } else if (activeTab === 'upcoming') {
      // Reset pagination on fresh load
      setUpcomingCursor(null);
      fetcher = fetchUpcomingEarnings();
    } else if (activeTab === 'season') {
      fetcher = fetchSeasonOverview();
    } else {
      setLoading(false);
      return;
    }

    fetcher
      .then((result) => {
        if (controller.signal.aborted) return;

        if (activeTab === 'recent') setRecentData(result);
        else if (activeTab === 'upcoming') {
          setUpcomingData(result);
          setUpcomingCursor(result.next_cursor || null);
        }
        else if (activeTab === 'season') setSeasonData(result);

        setUpdatedAt(result.updated_at || null);
        setLoading(false);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err.message || 'Failed to fetch earnings data');
        setLoading(false);
      });

    return () => controller.abort();
  }, [activeTab]);

  // Load more upcoming earnings (append to existing)
  const loadMoreUpcoming = useCallback(async () => {
    if (!upcomingCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const result = await fetchUpcomingEarnings(50, upcomingCursor);
      setUpcomingData(prev => {
        if (!prev) return result;
        return {
          ...result,
          events: [...(prev.events || []), ...(result.events || [])],
          count: (prev.count || 0) + (result.count || 0),
        };
      });
      setUpcomingCursor(result.next_cursor || null);
    } catch (err) {
      setError(err.message || 'Failed to load more earnings');
    } finally {
      setLoadingMore(false);
    }
  }, [upcomingCursor, loadingMore]);

  const hasMoreUpcoming = !!upcomingCursor;

  return { recentData, upcomingData, seasonData, loading, error, updatedAt, loadMoreUpcoming, loadingMore, hasMoreUpcoming };
}
