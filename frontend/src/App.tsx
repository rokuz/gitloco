import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api/client";
import { CommitDiff } from "./components/CommitDiff";
import { CommitList } from "./components/CommitList";

function App() {
  const [selectedSha, setSelectedSha] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });

  // Close drawer when selecting on mobile, after the selection has rendered.
  useEffect(() => {
    if (drawerOpen) setDrawerOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSha]);

  return (
    <div className="h-screen flex flex-col">
      <header className="flex items-center gap-2 border-b border-zinc-800 px-3 py-2 md:px-4">
        <button
          type="button"
          aria-label="Open commit list"
          onClick={() => setDrawerOpen(true)}
          className="md:hidden -ml-1 mr-1 inline-flex h-9 w-9 items-center justify-center rounded hover:bg-zinc-800 active:bg-zinc-700"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
            <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <h1 className="font-semibold text-zinc-100 shrink-0">GitLoco</h1>
          {health && (
            <span className="font-mono text-xs text-zinc-500 truncate">{health.repo}</span>
          )}
        </div>
        {health && <span className="hidden sm:inline text-xs text-zinc-500">v{health.version}</span>}
      </header>

      <div className="flex-1 flex min-h-0">
        <aside className="hidden md:block w-80 shrink-0 border-r border-zinc-800 overflow-y-auto">
          <CommitList selectedSha={selectedSha} onSelect={setSelectedSha} />
        </aside>

        {drawerOpen && (
          <div className="md:hidden fixed inset-0 z-40">
            <div
              className="absolute inset-0 bg-black/60"
              onClick={() => setDrawerOpen(false)}
              aria-hidden
            />
            <div className="absolute inset-y-0 left-0 w-[85%] max-w-sm bg-zinc-950 border-r border-zinc-800 shadow-xl overflow-y-auto">
              <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
                <span className="text-sm font-medium text-zinc-200">Commits</span>
                <button
                  type="button"
                  aria-label="Close"
                  onClick={() => setDrawerOpen(false)}
                  className="h-8 w-8 inline-flex items-center justify-center rounded hover:bg-zinc-800"
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
          {selectedSha ? (
            <div className="space-y-4">
              <h2 className="font-mono text-xs sm:text-sm text-zinc-400 break-all">
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

export default App;
