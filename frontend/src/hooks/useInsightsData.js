import { useState, useEffect, useRef } from 'react';
import { fetchInsights } from '../api/insightsApi';
import {
  normalizeQuarter,
  computeGrowthFields,
  computeValuationMultiples,
} from '../components/value-insights/mockData';

export default function useInsightsData(ticker) {
  const [data, setData] = useState(null);
  const [ratings, setRatings] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  useEffect(() => {
    if (!ticker) return;

    // Cancel previous in-flight request
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    fetchInsights(ticker)
      .then((result) => {
        if (controller.signal.aborted) return;

        if (!result.metrics || result.metrics.length === 0) {
          setData(null);
          setRatings(null);
          setError('no_data');
          setLoading(false);
          return;
        }

        // Normalize, sort, and compute growth fields
        const normalized = result.metrics
          .map(normalizeQuarter)
          .sort((a, b) => a.fiscal_date.localeCompare(b.fiscal_date));

        const withGrowth = computeGrowthFields(normalized);
        const withValuation = computeValuationMultiples(withGrowth);

        setData(withValuation);
        setRatings(result.ratings || null);
        setLoading(false);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err.message || 'Failed to fetch data');
        setLoading(false);
      });

    return () => controller.abort();
  }, [ticker]);

  return { data, ratings, loading, error };
}
