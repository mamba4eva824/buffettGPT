import { useState } from "react";
import { Search, Lightbulb, Globe, Settings, Paperclip, Mic, Waveform } from "lucide-react";
import { motion } from "framer-motion";

/**
 * SearchBar
 * - Recreates the UI from the screenshot with two toggle buttons on the left
 * - Uses Tailwind CSS + lucide-react icons
 * - Fully keyboard-accessible, with focus styles and aria labels
 */
export default function SearchBar() {
  const [mode, setMode] = useState<"search" | "idea">("search");
  const [query, setQuery] = useState("");

  return (
    <div className="w-full min-h-[60vh] grid place-items-start p-8 bg-white">
      <div className="w-full max-w-3xl">
        <label htmlFor="search" className="sr-only">Ask anything or @mention a Space</label>

        {/* Outer container */}
        <div className="relative flex items-center rounded-xl border border-slate-200 bg-white shadow-sm px-3 py-2 focus-within:border-slate-300">
          {/* Left toggles */}
          <div className="flex items-center gap-1 pr-2">
            <Toggle
              isActive={mode === "search"}
              onClick={() => setMode("search")}
              ariaLabel="Search mode"
              icon={<Search className="h-4 w-4" />}>
              
            </Toggle>
            <Toggle
              isActive={mode === "idea"}
              onClick={() => setMode("idea")}
              ariaLabel="Idea mode"
              icon={<Lightbulb className="h-4 w-4" />}>
              
            </Toggle>
            <span className="mx-1 h-6 w-px bg-slate-200" />
          </div>

          {/* Input */}
          <input
            id="search"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask anything or @mention a Space"
            className="peer block w-full bg-transparent text-[15px] placeholder:text-slate-400 focus:outline-none"
          />

          {/* Right-side icon actions */}
          <div className="ml-2 flex items-center gap-3 text-slate-500">
            <IconButton ariaLabel="Language or region">
              <Globe className="h-4 w-4" />
            </IconButton>
            <IconButton ariaLabel="Preferences">
              <Settings className="h-4 w-4" />
            </IconButton>
            <IconButton ariaLabel="Attach">
              <Paperclip className="h-4 w-4" />
            </IconButton>
            <IconButton ariaLabel="Record audio">
              <Mic className="h-4 w-4" />
            </IconButton>

            {/* Primary action button (voice) */}
            <motion.button
              whileTap={{ scale: 0.98 }}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-teal-600 text-white shadow-sm hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500/50">
              <Waveform className="h-5 w-5" />
              <span className="sr-only">Start voice</span>
            </motion.button>
          </div>
        </div>

        {/* Helper row (optional) */}
        <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
          <span className="rounded-md bg-slate-50 px-2 py-1">Mode: {mode === "search" ? "Search" : "Idea"}</span>
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-sans text-[10px]">/</kbd>
          <span>to focus</span>
        </div>
      </div>
    </div>
  );
}

// Small toggle button used for the left controls
function Toggle({ isActive, onClick, ariaLabel, icon }: {
  isActive: boolean;
  onClick: () => void;
  ariaLabel: string;
  icon: React.ReactNode;
}) {
  return (
    <motion.button
      type="button"
      aria-label={ariaLabel}
      onClick={onClick}
      whileTap={{ scale: 0.98 }}
      className={`inline-flex h-7 w-7 items-center justify-center rounded-md border text-slate-600 transition 
        ${isActive ? "border-teal-600 text-teal-700 bg-teal-50" : "border-slate-200 hover:bg-slate-50"}
      `}
    >
      {icon}
    </motion.button>
  );
}

// Shared small icon button
function IconButton({ ariaLabel, children }: { ariaLabel: string; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-300"
    >
      {children}
    </button>
  );
}
