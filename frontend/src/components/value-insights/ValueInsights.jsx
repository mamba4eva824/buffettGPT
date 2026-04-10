import { useState, useCallback, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CATEGORIES } from './mockData';
import { PANEL_MAP } from './panelMap';
import useInsightsData from '../../hooks/useInsightsData';
import sp500Companies from '../../data/sp500Companies.json';

const VALID_TABS = new Set(CATEGORIES.map(c => c.id));
const VALID_RANGES = new Set(['5Y', '3Y', '1Y']);

export default function ValueInsights() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Initialize state from URL search params
  const [activeCategory, setActiveCategory] = useState(() => {
    const tab = searchParams.get('tab');
    return tab && VALID_TABS.has(tab) ? tab : 'dashboard';
  });
  const [timeRange, setTimeRange] = useState(() => {
    const range = searchParams.get('range');
    return range && VALID_RANGES.has(range) ? range : '5Y';
  });
  const [ticker, setTicker] = useState(() => {
    const t = searchParams.get('ticker');
    return t ? t.toUpperCase() : 'AAPL';
  });
  const [searchInput, setSearchInput] = useState('');
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  // Sync state changes to URL search params
  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    params.set('mode', 'value-insights');
    if (ticker !== 'AAPL') { params.set('ticker', ticker); } else { params.delete('ticker'); }
    if (activeCategory !== 'dashboard') { params.set('tab', activeCategory); } else { params.delete('tab'); }
    if (timeRange !== '5Y') { params.set('range', timeRange); } else { params.delete('range'); }
    setSearchParams(params, { replace: true });
  }, [ticker, activeCategory, timeRange]); // eslint-disable-line react-hooks/exhaustive-deps

  const companyInfo = sp500Companies.find(c => c.ticker === ticker);
  const sector = companyInfo?.sector || '';
  const { data, ratings, latestPrice, sectorAggregate, postEarnings, executiveSummary, triggers, loading, error } = useInsightsData(ticker, sector);

  // Client-side fuzzy search over S&P 500 index
  const searchResults = useMemo(() => {
    const q = searchInput.trim().toUpperCase();
    if (!q) return sp500Companies.filter(c => c.ticker !== ticker).slice(0, 12);
    return sp500Companies
      .filter(c =>
        c.ticker !== ticker &&
        (c.ticker.includes(q) || c.name.toUpperCase().includes(q))
      )
      .slice(0, 12);
  }, [searchInput, ticker]);

  const handleSearch = useCallback((value) => {
    const t = (value || searchInput).trim().toUpperCase();
    const match = sp500Companies.find(c => c.ticker === t);
    if (match) {
      setTicker(match.ticker);
      setSearchInput('');
      setIsSearchFocused(false);
    } else if (t) {
      setTicker(t);
      setSearchInput('');
      setIsSearchFocused(false);
    }
  }, [searchInput]);

  const category = CATEGORIES.find(c => c.id === activeCategory);
  const PanelComponent = PANEL_MAP[activeCategory];
  const currency = data?.[0]?.currency || 'USD';

  return (
    <div className="flex flex-col h-full bg-sand-50 dark:bg-warm-950 text-sand-800 dark:text-warm-50 overflow-hidden">
      {/* Horizontal category nav bar */}
      <div className="shrink-0 border-b border-sand-200 dark:border-warm-800 bg-sand-50 dark:bg-warm-950">
        {/* Top row: ticker search + time range */}
        <div className="flex items-center gap-3 px-4 md:px-6 pt-2 pb-1 md:pb-2">
          {/* Ticker search — outside overflow container so dropdown isn't clipped */}
          <div className="shrink-0 flex items-center gap-2.5">
            <div className="relative">
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onFocus={() => setIsSearchFocused(true)}
                onBlur={() => setTimeout(() => setIsSearchFocused(false), 250)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSearch();
                  if (e.key === 'Escape') { setSearchInput(''); setIsSearchFocused(false); e.target.blur(); }
                }}
                placeholder={`Search (${ticker})`}
                className="w-44 md:w-52 bg-sand-100 dark:bg-warm-900 border border-sand-200 dark:border-warm-700 rounded-lg px-3 py-1.5 pr-16 text-sm font-serif font-bold text-vi-gold focus:outline-none focus:ring-2 focus:ring-vi-gold/50 focus:border-vi-gold transition-all placeholder:text-vi-gold/60 placeholder:font-normal placeholder:text-xs"
              />
              {/* Clear button — visible when there's input */}
              {searchInput && (
                <button
                  onMouseDown={(e) => { e.preventDefault(); setSearchInput(''); }}
                  className="absolute right-8 top-1/2 -translate-y-1/2 text-sand-400 hover:text-sand-600 dark:hover:text-warm-200 transition-colors"
                >
                  <span className="material-symbols-outlined text-sm">close</span>
                </button>
              )}
              <button
                onClick={() => handleSearch()}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-vi-gold/60 hover:text-vi-gold transition-colors"
              >
                <span className="material-symbols-outlined text-base">search</span>
              </button>
              {/* Dropdown suggestions */}
              {isSearchFocused && (
                <div className="absolute top-full left-0 mt-1 bg-sand-50 dark:bg-warm-900 border border-sand-200 dark:border-warm-700 rounded-lg shadow-lg z-50 p-2 w-72 max-h-64 overflow-y-auto">
                  {searchResults.map(c => (
                    <button
                      key={c.ticker}
                      onMouseDown={(e) => { e.preventDefault(); handleSearch(c.ticker); }}
                      className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-left hover:bg-sand-200 dark:hover:bg-warm-800 transition-colors"
                    >
                      <span className="text-[11px] font-bold text-vi-gold w-14 shrink-0">{c.ticker}</span>
                      <span className="text-[11px] text-sand-600 dark:text-warm-200 truncate">{c.name}</span>
                      <span className="ml-auto text-[10px] text-sand-400 dark:text-warm-400 shrink-0">{c.sector}</span>
                    </button>
                  ))}
                  {searchResults.length === 0 && (
                    <div className="px-2.5 py-2 text-[11px] text-sand-400 dark:text-warm-400">No matches found</div>
                  )}
                </div>
              )}
            </div>
            {companyInfo && (
              <span className="hidden lg:inline text-[11px] text-sand-500 dark:text-warm-300 truncate max-w-40">
                {companyInfo.name}
              </span>
            )}
          </div>

          <div className="flex-1" />

          {/* Time range + currency */}
          <div className="shrink-0 flex items-center gap-2">
            <div className="bg-sand-100 dark:bg-warm-900 rounded-lg flex items-center gap-1 p-0.5">
              {['5Y', '3Y', '1Y'].map(range => (
                <button
                  key={range}
                  onClick={() => setTimeRange(range)}
                  className={`px-2.5 py-1 rounded text-[11px] font-bold uppercase tracking-widest transition-all ${
                    timeRange === range
                      ? 'bg-vi-gold text-[#402d00]'
                      : 'text-sand-500 dark:text-warm-300 hover:text-vi-gold'
                  }`}
                >
                  {range}
                </button>
              ))}
            </div>
            <span className="text-[11px] font-bold text-vi-gold px-2">{currency}</span>
          </div>
        </div>

        {/* Category tabs — own row, horizontally scrollable */}
        <div className="overflow-x-auto scrollbar-none px-4 md:px-6 pb-2">
          <div className="flex items-center gap-1 w-max">
            {CATEGORIES.map(cat => {
              const isActive = cat.id === activeCategory;
              return (
                <button
                  key={cat.id}
                  onClick={() => setActiveCategory(cat.id)}
                  className={`shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all ${
                    isActive
                      ? 'bg-sand-200 dark:bg-warm-800 text-vi-gold border-b-2 border-vi-gold'
                      : 'text-sand-500 dark:text-warm-300 hover:bg-sand-100 dark:hover:bg-warm-900 hover:text-vi-gold'
                  }`}
                >
                  <span className="material-symbols-outlined text-sm">{cat.icon}</span>
                  <span>{cat.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Main scrollable content */}
      <main className="flex-1 p-4 md:p-8 overflow-y-auto">
        {/* Page header */}
        <header className="mb-8 md:mb-10">
          <h1 className="font-serif text-3xl md:text-4xl font-bold tracking-tight mb-1">
            {category?.title}
          </h1>
          <p className="text-sand-500 dark:text-warm-300 font-medium max-w-xl text-sm">
            {category?.description}
          </p>
        </header>

        {/* Loading state */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-vi-gold/30 border-t-vi-gold rounded-full animate-spin" />
              <span className="text-sm text-sand-500 dark:text-warm-300">Loading {ticker} data...</span>
            </div>
          </div>
        )}

        {/* Error / no data state */}
        {!loading && error && (
          <div className="flex items-center justify-center py-20">
            <div className="flex flex-col items-center gap-2 text-center">
              <span className="material-symbols-outlined text-3xl text-sand-400 dark:text-warm-500">
                {error === 'no_data' ? 'search_off' : 'error_outline'}
              </span>
              <p className="text-sm font-semibold text-sand-600 dark:text-warm-200">
                {error === 'no_data'
                  ? `No financial data available for ${ticker}`
                  : 'Failed to load data'}
              </p>
              <p className="text-xs text-sand-400 dark:text-warm-400 max-w-xs">
                {error === 'no_data'
                  ? 'This ticker may not have been processed yet. Try a major S&P 500 company.'
                  : error}
              </p>
            </div>
          </div>
        )}

        {/* Active category panel */}
        {!loading && !error && data && PanelComponent && (
          <PanelComponent
            data={data}
            ratings={ratings}
            latestPrice={latestPrice}
            postEarnings={postEarnings}
            timeRange={timeRange}
            sectorAggregate={sectorAggregate}
            sector={sector}
            onSelectCategory={setActiveCategory}
            triggers={triggers}
            executiveSummary={executiveSummary}
          />
        )}

        {/* Footer */}
        <footer className="mt-12 flex flex-col md:flex-row justify-between items-center text-sand-400 dark:text-warm-400 text-[10px] font-bold uppercase tracking-widest gap-2">
          <div className="flex gap-8">
            <span>Source: SEC Filings / FMP</span>
            {data && <span>Quarters: {data.length}</span>}
          </div>
          <div className="flex gap-4">
            <span className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${data ? 'bg-vi-sage' : 'bg-sand-300 dark:bg-warm-600'}`} />
              {data ? 'Live Data' : 'No Data'}
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}
