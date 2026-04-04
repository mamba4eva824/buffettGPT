import { useState, useEffect, useRef } from 'react';
import { fetchInsights } from '../api/insightsApi';
import {
  normalizeQuarter,
  computeGrowthFields,
  computeValuationMultiples,
} from '../components/value-insights/mockData';

export default function useInsightsData(ticker, sector = '') {
  const [data, setData] = useState(null);
  const [ratings, setRatings] = useState(null);
  const [latestPrice, setLatestPrice] = useState(null);
  const [sectorAggregate, setSectorAggregate] = useState(null);
  const [postEarnings, setPostEarnings] = useState(null);
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

    fetchInsights(ticker, sector)
      .then((result) => {
        if (controller.signal.aborted) return;

        if (!result.metrics || result.metrics.length === 0) {
          setData(null);
          setRatings(null);
          setLatestPrice(null);
          setSectorAggregate(null);
          setPostEarnings(null);
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

        // Use live price if available, otherwise fall back to latest quarter's stock price
        if (result.latest_price) {
          setLatestPrice(result.latest_price);
        } else {
          const lastQ = withValuation[withValuation.length - 1];
          const fallbackPrice = lastQ?.valuation?.stock_price;
          setLatestPrice(fallbackPrice ? { price: fallbackPrice, date: lastQ.fiscal_date, source: 'quarterly' } : null);
        }
        setSectorAggregate(result.sector_aggregate || null);
        setPostEarnings(result.post_earnings || null);
        setLoading(false);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err.message || 'Failed to fetch data');
        setLoading(false);
      });

    return () => controller.abort();
  }, [ticker, sector]);

  return { data, ratings, latestPrice, sectorAggregate, postEarnings, loading, error };
}
