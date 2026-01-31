import { useState, useCallback, useRef } from 'react';

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

  const search = useCallback((query) => {
    // Clear any pending search
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    // Don't search for very short queries
    if (!query || query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);

    // Debounce the search
    debounceRef.current = setTimeout(async () => {
      try {
        // TODO: Implement actual API call to search companies
        // For now, return empty results
        setResults([]);
        setError(null);
      } catch (err) {
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
