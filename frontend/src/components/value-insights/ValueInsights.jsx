import { useState, useCallback } from 'react';
import { MOCK_QUARTERS, MOCK_RATINGS, CATEGORIES } from './mockData';
import { PANEL_MAP } from './panelMap';

const EXAMPLE_TICKERS = ['AAPL', 'MSFT', 'AMZN', 'GOOGL', 'BRK.B', 'NVDA', 'JPM', 'V'];

export default function ValueInsights() {
  const [activeCategory, setActiveCategory] = useState('dashboard');
  const [timeRange, setTimeRange] = useState('5Y');
  const [ticker, setTicker] = useState('AAPL');
  const [searchInput, setSearchInput] = useState('');
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  const handleSearch = useCallback((value) => {
    const t = (value || searchInput).trim().toUpperCase();
    if (t) {
      setTicker(t);
      setSearchInput('');
      setIsSearchFocused(false);
    }
  }, [searchInput]);

  const category = CATEGORIES.find(c => c.id === activeCategory);
  const PanelComponent = PANEL_MAP[activeCategory];

  return (
    <div className="flex flex-col h-full bg-sand-50 dark:bg-warm-950 text-sand-800 dark:text-warm-50 overflow-hidden">
      {/* Horizontal category nav bar */}
      <div className="shrink-0 border-b border-sand-200 dark:border-warm-800 bg-sand-50 dark:bg-warm-950">
        <div className="flex items-center gap-3 px-4 md:px-6 py-2 overflow-x-auto scrollbar-none">
          {/* Ticker badge */}
          <div className="shrink-0 flex items-center gap-2.5 pr-4 border-r border-sand-200 dark:border-warm-800 mr-1">
            <div className="relative">
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onFocus={() => setIsSearchFocused(true)}
                onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder={ticker}
                className="w-24 bg-sand-100 dark:bg-warm-900 border border-sand-200 dark:border-warm-700 rounded-lg px-3 py-1.5 pr-8 text-sm font-serif font-bold text-vi-gold focus:outline-none focus:ring-2 focus:ring-vi-gold/50 focus:border-vi-gold transition-all placeholder:text-vi-gold"
              />
              <button
                onClick={() => handleSearch()}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-vi-gold/60 hover:text-vi-gold transition-colors"
              >
                <span className="material-symbols-outlined text-base">search</span>
              </button>
              {/* Dropdown suggestions */}
              {isSearchFocused && (
                <div className="absolute top-full left-0 mt-1 bg-sand-50 dark:bg-warm-900 border border-sand-200 dark:border-warm-700 rounded-lg shadow-lg z-50 p-2 flex flex-wrap gap-1.5 w-56">
                  {EXAMPLE_TICKERS.filter(t => t !== ticker).map(t => (
                    <button
                      key={t}
                      onMouseDown={(e) => { e.preventDefault(); handleSearch(t); }}
                      className="px-2.5 py-1 bg-sand-200 dark:bg-warm-800 rounded text-[11px] font-semibold text-sand-600 dark:text-warm-200 hover:text-vi-gold hover:bg-sand-300 dark:hover:bg-warm-700 transition-colors"
                    >
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Category tabs */}
          {CATEGORIES.map(cat => {
            const isActive = cat.id === activeCategory;
            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all ${
                  isActive
                    ? 'bg-sand-200 dark:bg-warm-800 text-vi-gold border-b-2 border-vi-gold'
                    : 'text-sand-500 dark:text-warm-300 hover:bg-sand-100 dark:hover:bg-warm-900 hover:text-vi-gold'
                }`}
              >
                <span className="material-symbols-outlined text-base">{cat.icon}</span>
                <span className="hidden sm:inline">{cat.label}</span>
              </button>
            );
          })}

          {/* Spacer */}
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
            <span className="text-[11px] font-bold text-vi-gold px-2">USD</span>
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

        {/* Active category panel */}
        {PanelComponent && (
          <PanelComponent
            data={MOCK_QUARTERS}
            ratings={MOCK_RATINGS}
            timeRange={timeRange}
            onSelectCategory={setActiveCategory}
          />
        )}

        {/* Footer */}
        <footer className="mt-12 flex flex-col md:flex-row justify-between items-center text-sand-400 dark:text-warm-400 text-[10px] font-bold uppercase tracking-widest gap-2">
          <div className="flex gap-8">
            <span>Last Updated: 2025-06-28</span>
            <span>Source: SEC Filings / FMP</span>
          </div>
          <div className="flex gap-4">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-vi-sage" />
              Mock Data
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}
