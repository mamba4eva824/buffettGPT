import { useState, useEffect, useRef } from 'react';
import { fetchRecentEarnings, fetchUpcomingEarnings, fetchSeasonOverview } from '../api/earningsApi';

export default function useEarningsData(activeTab) {
  const [recentData, setRecentData] = useState(null);
  const [upcomingData, setUpcomingData] = useState(null);
  const [seasonData, setSeasonData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const abortRef = useRef(null);

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
        else if (activeTab === 'upcoming') setUpcomingData(result);
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

  return { recentData, upcomingData, seasonData, loading, error, updatedAt };
}
