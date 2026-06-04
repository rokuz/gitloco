import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api/client";
import { CommitDiff } from "./components/CommitDiff";
import { CommitList } from "./components/CommitList";
import { OrphanThreads } from "./components/OrphanThreads";
import { applyTheme, initialTheme, type Theme } from "./utils/theme";

function App() {
  const [selectedSha, setSelectedSha] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(() => initialTheme());
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Close drawer when selecting on mobile, after the selection has rendered.
  useEffect(() => {
    if (drawerOpen) setDrawerOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSha]);

  return (
    <div className="h-screen flex flex-col bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="flex items-center gap-2 border-b border-zinc-200 dark:border-zinc-800 px-3 py-2 md:px-4">
        <button
          type="button"
          aria-label="Open commit list"
          onClick={() => setDrawerOpen(true)}
          className="md:hidden -ml-1 mr-1 inline-flex h-9 w-9 items-center justify-center rounded hover:bg-zinc-100 active:bg-zinc-200 dark:hover:bg-zinc-800 dark:active:bg-zinc-700"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
            <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <h1 className="font-semibold shrink-0">GitLoco</h1>
          {health && (
            <span className="font-mono text-xs text-zinc-500 dark:text-zinc-500 truncate">{health.repo}</span>
          )}
        </div>
        <ThemeToggle theme={theme} onChange={setTheme} />
        {health && <span className="hidden sm:inline text-xs text-zinc-500">v{health.version}</span>}
      </header>

      <div className="flex-1 flex min-h-0">
        <aside className="hidden md:block w-80 shrink-0 border-r border-zinc-200 dark:border-zinc-800 overflow-y-auto">
          <CommitList selectedSha={selectedSha} onSelect={setSelectedSha} />
        </aside>

        {drawerOpen && (
          <div className="md:hidden fixed inset-0 z-40">
            <div
              className="absolute inset-0 bg-black/40 dark:bg-black/60"
              onClick={() => setDrawerOpen(false)}
              aria-hidden
            />
            <div className="absolute inset-y-0 left-0 w-[85%] max-w-sm bg-white dark:bg-zinc-950 border-r border-zinc-200 dark:border-zinc-800 shadow-xl overflow-y-auto">
              <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-200 dark:border-zinc-800">
                <span className="text-sm font-medium text-zinc-700 dark:text-zinc-200">Commits</span>
                <button
                  type="button"
                  aria-label="Close"
                  onClick={() => setDrawerOpen(false)}
                  className="h-8 w-8 inline-flex items-center justify-center rounded hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
                    <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
              <CommitList selectedSha={selectedSha} onSelect={setSelectedSha} />
            </div>
          </div>
        )}

        <main className="flex-1 overflow-y-auto p-3 md:p-6">
          <OrphanThreads />
          {selectedSha ? (
            <div className="space-y-4">
              <h2 className="font-mono text-xs sm:text-sm text-zinc-600 dark:text-zinc-400 break-all">
                {selectedSha}
              </h2>
              <CommitDiff sha={selectedSha} />
            </div>
          ) : (
            <p className="text-zinc-500 text-sm">
              <span className="md:hidden">Tap ☰ to pick a commit.</span>
              <span className="hidden md:inline">Select a commit from the left.</span>
            </p>
          )}
        </main>
      </div>
    </div>
  );
}

function ThemeToggle({
  theme,
  onChange,
}: {
  theme: Theme;
  onChange: (t: Theme) => void;
}) {
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      onClick={() => onChange(next)}
      className="inline-flex h-8 w-8 items-center justify-center rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300"
    >
      {theme === "dark" ? (
        // Sun
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
          <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      ) : (
        // Moon
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

export default App;
