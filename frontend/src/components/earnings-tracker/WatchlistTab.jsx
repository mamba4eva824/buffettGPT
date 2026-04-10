import { useState, useRef, useEffect } from 'react';

const CARD = 'bg-sand-100 dark:bg-warm-900 rounded-xl';

const POPULAR_TICKERS = [
  { ticker: 'AAPL', name: 'Apple Inc.' },
  { ticker: 'MSFT', name: 'Microsoft Corp.' },
  { ticker: 'AMZN', name: 'Amazon.com Inc.' },
  { ticker: 'GOOGL', name: 'Alphabet Inc.' },
  { ticker: 'NVDA', name: 'NVIDIA Corp.' },
  { ticker: 'META', name: 'Meta Platforms Inc.' },
  { ticker: 'TSLA', name: 'Tesla Inc.' },
  { ticker: 'JPM', name: 'JPMorgan Chase' },
  { ticker: 'V', name: 'Visa Inc.' },
  { ticker: 'UNH', name: 'UnitedHealth Group' },
  { ticker: 'JNJ', name: 'Johnson & Johnson' },
  { ticker: 'WMT', name: 'Walmart Inc.' },
  { ticker: 'PG', name: 'Procter & Gamble' },
  { ticker: 'MA', name: 'Mastercard Inc.' },
  { ticker: 'HD', name: 'Home Depot Inc.' },
  { ticker: 'DIS', name: 'Walt Disney Co.' },
  { ticker: 'NFLX', name: 'Netflix Inc.' },
  { ticker: 'CRM', name: 'Salesforce Inc.' },
  { ticker: 'COST', name: 'Costco Wholesale' },
  { ticker: 'PEP', name: 'PepsiCo Inc.' },
];

function DeltaChip({ value, suffix = '%' }) {
  if (value == null) return <span className="text-sand-400 dark:text-warm-500">—</span>;
  const isPositive = value >= 0;
  const color = isPositive ? 'text-vi-sage' : 'text-vi-rose';
  const sign = isPositive ? '+' : '';
  return <span className={`font-bold ${color}`}>{sign}{value.toFixed(2)}{suffix}</span>;
}

function BeatMissBadge({ beat }) {
  if (beat == null) return <span className="text-sand-400 dark:text-warm-500 text-xs">—</span>;
  return beat ? (
    <span className="px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-widest bg-vi-sage/20 text-vi-sage">Beat</span>
  ) : (
    <span className="px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-widest bg-vi-rose/20 text-vi-rose">Miss</span>
  );
}

export default function WatchlistTab({ data, onAddTicker, onRemoveTicker, onSelectTicker, addLoading }) {
  const [query, setQuery] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [pendingTicker, setPendingTicker] = useState(null);
  const dropdownRef = useRef(null);
  const inputRef = useRef(null);

  const items = data?.watchlist || [];

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target) &&
          inputRef.current && !inputRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Clear pending ticker when addLoading finishes
  useEffect(() => {
    if (!addLoading) setPendingTicker(null);
  }, [addLoading]);

  // Compute search results
  const searchResults = (() => {
    if (!query.trim()) return [];
    const q = query.trim().toLowerCase();
    const matches = POPULAR_TICKERS.filter(
      t => t.ticker.toLowerCase().includes(q) || t.name.toLowerCase().includes(q)
    ).slice(0, 8);

    // If query looks like a ticker (1-5 uppercase letters) and isn't already in results, offer custom add
    const upperQuery = query.trim().toUpperCase();
    const isTickerLike = /^[A-Z]{1,5}$/.test(upperQuery);
    const alreadyInResults = matches.some(m => m.ticker === upperQuery);
    if (isTickerLike && !alreadyInResults) {
      matches.push({ ticker: upperQuery, name: `Add ${upperQuery}`, isCustom: true });
    }

    return matches.slice(0, 8);
  })();

  const handleSelect = async (ticker) => {
    setPendingTicker(ticker);
    setQuery('');
    setShowDropdown(false);
    try {
      await onAddTicker(ticker);
    } catch {
      // error handled in parent
    }
  };

  const handleRemove = (ticker) => {
    if (window.confirm(`Remove ${ticker} from your watchlist?`)) {
      onRemoveTicker(ticker);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className={`${CARD} p-4`}>
        <div className="relative">
          <div className="flex items-center gap-2 px-3 py-2 bg-sand-50 dark:bg-warm-950 rounded-lg border border-sand-200 dark:border-warm-700 focus-within:border-vi-gold transition-colors">
            <span className="material-symbols-outlined text-sand-400 dark:text-warm-500 text-lg">search</span>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setShowDropdown(true); }}
              onFocus={() => { if (query.trim()) setShowDropdown(true); }}
              placeholder="Search S&P 500 ticker..."
              className="flex-1 bg-transparent text-sm text-sand-800 dark:text-warm-50 placeholder-sand-400 dark:placeholder-warm-500 outline-none"
            />
            {addLoading && pendingTicker && (
              <span className="text-xs text-sand-400 dark:text-warm-500 flex items-center gap-1">
                <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                Adding {pendingTicker}...
              </span>
            )}
          </div>

          {/* Dropdown */}
          {showDropdown && searchResults.length > 0 && (
            <div
              ref={dropdownRef}
              className="absolute z-20 mt-1 w-full bg-sand-50 dark:bg-warm-900 border border-sand-200 dark:border-warm-700 rounded-lg shadow-lg overflow-hidden"
            >
              {searchResults.map((item) => (
                <button
                  key={item.ticker}
                  onClick={() => handleSelect(item.ticker)}
                  disabled={addLoading}
                  className="w-full px-4 py-2.5 text-left text-sm hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors flex items-center gap-2 disabled:opacity-50"
                >
                  <span className="font-bold text-vi-gold">{item.ticker}</span>
                  <span className="text-sand-500 dark:text-warm-400 truncate">{item.isCustom ? item.name : item.name}</span>
                  {item.isCustom && (
                    <span className="ml-auto material-symbols-outlined text-sm text-sand-400 dark:text-warm-500">add_circle</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Watchlist table */}
      {items.length === 0 ? (
        <div className={`${CARD} p-8 text-center`}>
          <span className="material-symbols-outlined text-4xl text-sand-300 dark:text-warm-700 mb-3 block">bookmark_border</span>
          <p className="text-sand-500 dark:text-warm-400">Your watchlist is empty.</p>
          <p className="text-sm text-sand-400 dark:text-warm-500 mt-1">Search for a ticker above to start tracking.</p>
        </div>
      ) : (
        <div className={`${CARD} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-sand-200/50 dark:bg-warm-800/50">
                  <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300">Ticker / Company</th>
                  <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 hidden lg:table-cell">Sector</th>
                  <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300">Watching Since</th>
                  <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 text-right">Price &Delta;</th>
                  <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 text-right">EPS &Delta;</th>
                  <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 text-center">Result</th>
                  <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
                {items.map((item, i) => (
                  <tr
                    key={item.ticker}
                    className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors cursor-pointer ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}
                    onClick={() => onSelectTicker?.(item.ticker)}
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-vi-gold">{item.ticker}</span>
                        <span className="text-sm text-sand-500 dark:text-warm-400 hidden md:inline truncate max-w-[180px]">{item.company_name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-sand-500 dark:text-warm-400 hidden lg:table-cell">{item.sector || '—'}</td>
                    <td className="px-6 py-4 text-sm text-sand-600 dark:text-warm-200">{formatDate(item.watched_since || item.added_at)}</td>
                    <td className="px-6 py-4 text-right">
                      <DeltaChip value={item.price_change_pct} />
                    </td>
                    <td className="px-6 py-4 text-right">
                      <DeltaChip value={item.eps_change_pct} />
                    </td>
                    <td className="px-6 py-4 text-center">
                      <BeatMissBadge beat={item.eps_beat} />
                    </td>
                    <td className="px-6 py-4 text-center">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleRemove(item.ticker); }}
                        className="text-sand-400 dark:text-warm-500 hover:text-vi-rose transition-colors"
                        title={`Remove ${item.ticker}`}
                      >
                        <span className="material-symbols-outlined text-lg">delete</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
