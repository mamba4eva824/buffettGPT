import { useState, useCallback, useRef } from 'react';

const RESEARCH_LAMBDA_URL = import.meta.env.VITE_RESEARCH_LAMBDA_URL || '';

/**
 * useCompanySearch - Hook for company ticker search autocomplete
 *
 * Provides debounced search functionality for finding companies by name or ticker.
 */
export function useCompanySearch(debounceMs = 300) {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);
  const abortRef = useRef(null);

  const search = useCallback((query) => {
    // Clear any pending search
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    // Abort any in-flight request
    if (abortRef.current) {
      abortRef.current.abort();
    }

    // Don't search for very short queries
    if (!query || query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    if (!RESEARCH_LAMBDA_URL) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);

    // Debounce the search
    debounceRef.current = setTimeout(async () => {
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch(
          `${RESEARCH_LAMBDA_URL}/reports/search?q=${encodeURIComponent(query)}`,
          { signal: controller.signal }
        );

        if (!response.ok) {
          throw new Error(`Search failed (${response.status})`);
        }

        const data = await response.json();
        setResults(data.results || []);
        setError(null);
      } catch (err) {
        if (err.name === 'AbortError') return;
        console.error('Company search error:', err);
        setError(err.message);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, debounceMs);
  }, [debounceMs]);

  const clearResults = useCallback(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    setResults([]);
    setLoading(false);
    setError(null);
  }, []);

  return {
    results,
    loading,
    error,
    search,
    clearResults,
  };
}

export default useCompanySearch;
