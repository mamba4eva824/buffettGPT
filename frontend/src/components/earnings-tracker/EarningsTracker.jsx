import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import useEarningsData from '../../hooks/useEarningsData';
import useWatchlist from '../../hooks/useWatchlist';
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
          <h1 className="text-lg font-serif font-bold text-sand-800 dark:text-warm-50">Earnings Tracker</h1>
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
