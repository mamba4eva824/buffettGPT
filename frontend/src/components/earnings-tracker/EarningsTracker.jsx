import { useState, useCallback, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import useEarningsData from '../../hooks/useEarningsData';
import useWatchlist from '../../hooks/useWatchlist';
import sp500Companies from '../../data/sp500Companies.json';
import RecentFeed from './RecentFeed';
import UpcomingCalendar from './UpcomingCalendar';
import SeasonHeatmap from './SeasonHeatmap';
import WatchlistTab from './WatchlistTab';

const BASE_TABS = [
  { id: 'recent', label: 'Recent', icon: 'breaking_news' },
  { id: 'upcoming', label: 'Upcoming', icon: 'calendar_month' },
  { id: 'season', label: 'Season Overview', icon: 'bar_chart' },
];

const WATCHLIST_TAB = { id: 'watchlist', label: 'Watchlist', icon: 'bookmark' };

function formatRelativeTime(isoString) {
  if (!isoString) return null;
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export default function EarningsTracker({ onNavigateToInsights, isAuthenticated, token }) {
  const [searchParams, setSearchParams] = useSearchParams();

  const tabs = isAuthenticated ? [...BASE_TABS, WATCHLIST_TAB] : BASE_TABS;

  const [activeTab, setActiveTab] = useState(() => {
    const tab = searchParams.get('etab');
    const allValid = new Set(['recent', 'upcoming', 'season', ...(isAuthenticated ? ['watchlist'] : [])]);
    return tab && allValid.has(tab) ? tab : 'recent';
  });

  // Sync tab to URL
  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    params.set('mode', 'earnings-tracker');
    if (activeTab !== 'recent') { params.set('etab', activeTab); } else { params.delete('etab'); }
    setSearchParams(params, { replace: true });
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const { recentData, upcomingData, seasonData, loading, error, updatedAt, loadMoreUpcoming, loadingMore, hasMoreUpcoming } = useEarningsData(activeTab);

  const { watchlistData, loading: watchlistLoading, error: watchlistError, addTicker, removeTicker } = useWatchlist(token);
  const [addLoading, setAddLoading] = useState(false);

  const handleSelectTicker = useCallback((ticker) => {
    if (onNavigateToInsights) {
      onNavigateToInsights(ticker);
    }
  }, [onNavigateToInsights]);

  // Company search
  const [searchInput, setSearchInput] = useState('');
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  // Build earnings date lookup from upcoming data
  const earningsDateMap = useMemo(() => {
    const map = {};
    for (const e of upcomingData?.events || []) {
      if (e.ticker && e.earnings_date) map[e.ticker] = e.earnings_date;
    }
    return map;
  }, [upcomingData]);

  const searchResults = useMemo(() => {
    const q = searchInput.trim().toUpperCase();
    const filtered = q
      ? sp500Companies.filter(c => c.ticker.includes(q) || c.name.toUpperCase().includes(q))
      : sp500Companies;
    return filtered.slice(0, 12).map(c => ({
      ...c,
      earnings_date: earningsDateMap[c.ticker] || null,
    }));
  }, [searchInput, earningsDateMap]);

  const handleSearchSelect = useCallback((value) => {
    const t = (value || searchInput).trim().toUpperCase();
    if (t) {
      handleSelectTicker(t);
      setSearchInput('');
      setIsSearchFocused(false);
    }
  }, [searchInput, handleSelectTicker]);

  const handleAddTicker = useCallback(async (ticker) => {
    setAddLoading(true);
    try {
      await addTicker(ticker);
    } catch {
      // error is set in the hook
    } finally {
      setAddLoading(false);
    }
  }, [addTicker]);

  return (
    <div className="flex flex-col h-full bg-sand-50 dark:bg-warm-950 text-sand-800 dark:text-warm-50 overflow-hidden">
      {/* Tab Navigation */}
      <div className="shrink-0 border-b border-sand-200 dark:border-warm-800 bg-sand-50 dark:bg-warm-950">
        <div className="flex items-center gap-3 px-4 md:px-6 py-3">
          <span className="material-symbols-outlined text-vi-gold text-xl">candlestick_chart</span>
          <h1 className="text-lg font-serif font-bold text-sand-800 dark:text-warm-50 hidden md:block">Earnings Tracker</h1>
          {/* Company Search */}
          <div className="relative">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onFocus={() => setIsSearchFocused(true)}
              onBlur={() => setTimeout(() => setIsSearchFocused(false), 250)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSearchSelect();
                if (e.key === 'Escape') { setSearchInput(''); setIsSearchFocused(false); e.target.blur(); }
              }}
              placeholder="Search company..."
              className="w-36 md:w-48 bg-sand-100 dark:bg-warm-900 border border-sand-200 dark:border-warm-700 rounded-lg px-3 py-1.5 pr-8 text-sm text-sand-800 dark:text-warm-50 focus:outline-none focus:ring-2 focus:ring-vi-gold/50 focus:border-vi-gold transition-all placeholder:text-sand-400 dark:placeholder:text-warm-500 placeholder:text-xs"
            />
            {searchInput ? (
              <button
                onMouseDown={(e) => { e.preventDefault(); setSearchInput(''); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-sand-400 hover:text-sand-600 dark:hover:text-warm-200 transition-colors"
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            ) : (
              <span className="absolute right-2 top-1/2 -translate-y-1/2 text-sand-400 dark:text-warm-500">
                <span className="material-symbols-outlined text-sm">search</span>
              </span>
            )}
            {isSearchFocused && (
              <div className="absolute top-full left-0 mt-1 bg-sand-50 dark:bg-warm-900 border border-sand-200 dark:border-warm-700 rounded-lg shadow-lg z-50 p-2 w-72 max-h-64 overflow-y-auto">
                {searchResults.map(c => (
                  <button
                    key={c.ticker}
                    onMouseDown={(e) => { e.preventDefault(); handleSearchSelect(c.ticker); }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-left hover:bg-sand-200 dark:hover:bg-warm-800 transition-colors"
                  >
                    <span className="text-[11px] font-bold text-vi-gold w-14 shrink-0">{c.ticker}</span>
                    <span className="text-[11px] text-sand-600 dark:text-warm-200 truncate">{c.name}</span>
                    {c.earnings_date ? (
                      <span className="ml-auto text-[10px] text-vi-sage font-semibold shrink-0">Reports {c.earnings_date}</span>
                    ) : (
                      <span className="ml-auto text-[10px] text-sand-400 dark:text-warm-400 shrink-0">{c.sector}</span>
                    )}
                  </button>
                ))}
                {searchResults.length === 0 && (
                  <div className="px-2.5 py-2 text-[11px] text-sand-400 dark:text-warm-400">No matches found</div>
                )}
              </div>
            )}
          </div>
          <div className="ml-auto flex items-center bg-sand-100 dark:bg-warm-900 rounded-lg p-0.5">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 md:px-4 py-1.5 rounded-md text-xs font-semibold tracking-wide transition-all flex items-center gap-1.5 ${
                  activeTab === tab.id
                    ? 'bg-vi-gold text-[#402d00] shadow-sm'
                    : 'text-sand-500 dark:text-warm-300 hover:text-sand-700 dark:hover:text-warm-100'
                }`}
              >
                <span className="material-symbols-outlined text-sm hidden md:inline">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
          {updatedAt && !loading && (
            <span className="hidden md:inline text-xs text-sand-400 dark:text-warm-500 ml-2" title={updatedAt}>
              Updated {formatRelativeTime(updatedAt)}
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-4 md:p-8 overflow-y-auto">
        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="flex items-center gap-3 text-sand-500 dark:text-warm-400">
              <span className="material-symbols-outlined animate-spin">progress_activity</span>
              <span className="text-sm">Loading earnings data...</span>
            </div>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="bg-vi-rose/10 rounded-xl p-6 text-center">
            <span className="material-symbols-outlined text-vi-rose text-2xl mb-2 block">error</span>
            <p className="text-sm text-vi-rose">{error}</p>
          </div>
        )}

        {/* Tab Content */}
        {!loading && !error && (
          <>
            {activeTab === 'recent' && (
              <RecentFeed data={recentData} onSelectTicker={handleSelectTicker} />
            )}
            {activeTab === 'upcoming' && (
              <UpcomingCalendar data={upcomingData} onSelectTicker={handleSelectTicker} onLoadMore={loadMoreUpcoming} loadingMore={loadingMore} hasMore={hasMoreUpcoming} />
            )}
            {activeTab === 'season' && (
              <SeasonHeatmap data={seasonData} />
            )}
          </>
        )}

        {/* Watchlist Tab (independent of earnings loading/error) */}
        {activeTab === 'watchlist' && isAuthenticated && (
          <>
            {watchlistLoading && (
              <div className="flex items-center justify-center py-12">
                <div className="flex items-center gap-3 text-sand-500 dark:text-warm-400">
                  <span className="material-symbols-outlined animate-spin">progress_activity</span>
                  <span className="text-sm">Loading watchlist...</span>
                </div>
              </div>
            )}
            {watchlistError && !watchlistLoading && (
              <div className="bg-vi-rose/10 rounded-xl p-6 text-center">
                <span className="material-symbols-outlined text-vi-rose text-2xl mb-2 block">error</span>
                <p className="text-sm text-vi-rose">{watchlistError}</p>
              </div>
            )}
            {!watchlistLoading && !watchlistError && (
              <WatchlistTab
                data={watchlistData}
                onAddTicker={handleAddTicker}
                onRemoveTicker={removeTicker}
                onSelectTicker={handleSelectTicker}
                addLoading={addLoading}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
