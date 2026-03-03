"use client";

import { useTheme } from "./ThemeProvider";
import type { Decision } from "@/lib/types";

const statusFilters: { label: string; value: Decision | "ALL"; dot?: string }[] = [
  { label: "All", value: "ALL" },
  { label: "Pass", value: "PASS", dot: "bg-status-pass" },
  { label: "Review", value: "REVIEW_REQUIRED", dot: "bg-status-review" },
  { label: "Fail", value: "FAIL", dot: "bg-status-fail" },
];

interface TopBarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: Decision | "ALL";
  onStatusFilterChange: (filter: Decision | "ALL") => void;
  onMenuToggle: () => void;
}

export default function TopBar({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  onMenuToggle,
}: TopBarProps) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-30 h-14 flex items-center gap-3 px-4 lg:px-6 bg-bg-light-surface/90 dark:bg-bg-primary/90 backdrop-blur-xl border-b border-border-light dark:border-border-dark">
      <button
        onClick={onMenuToggle}
        className="lg:hidden p-2 -ml-1 rounded-lg text-text-light-secondary dark:text-text-secondary hover:bg-bg-light-hover dark:hover:bg-bg-hover transition-colors"
        aria-label="Toggle menu"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
        </svg>
      </button>

      <div className="flex-1 max-w-sm relative group">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-light-muted dark:text-text-muted group-focus-within:text-accent transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
        <input
          type="text"
          placeholder="Search..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full h-9 pl-9 pr-3 text-[13px] rounded-xl
            bg-bg-light-elevated dark:bg-white/4
            border border-border-light dark:border-border-dark
            text-text-light-primary dark:text-text-primary
            placeholder:text-text-light-muted dark:placeholder:text-text-muted
            focus:border-accent/30 focus:ring-1 focus:ring-accent/10
            transition-all duration-150 outline-none"
        />
      </div>

      <div className="hidden md:flex items-center gap-0.5 rounded-xl p-0.5 bg-bg-light-elevated dark:bg-white/3">
        {statusFilters.map((sf) => {
          const active = statusFilter === sf.value;
          return (
            <button
              key={sf.value}
              onClick={() => onStatusFilterChange(sf.value)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium rounded-lg transition-all duration-150 ${
                active
                  ? "bg-bg-light-surface dark:bg-accent/12 text-text-light-primary dark:text-accent-secondary shadow-sm"
                  : "text-text-light-muted dark:text-text-muted hover:text-text-light-secondary dark:hover:text-text-secondary"
              }`}
            >
              {sf.dot && (
                <span className={`w-1.5 h-1.5 rounded-full ${sf.dot} ${active ? "opacity-100" : "opacity-40"}`} />
              )}
              {sf.label}
            </button>
          );
        })}
      </div>

      <button
        onClick={toggleTheme}
        className="p-2 rounded-lg text-text-light-secondary dark:text-text-secondary hover:bg-bg-light-hover dark:hover:bg-bg-hover transition-colors"
        aria-label="Toggle theme"
      >
        {theme === "dark" ? (
          <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
          </svg>
        ) : (
          <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
          </svg>
        )}
      </button>
    </header>
  );
}
