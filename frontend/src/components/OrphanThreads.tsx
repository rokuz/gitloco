import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { ThreadView } from "./ThreadView";

/**
 * Threads whose anchored commit is no longer reachable (e.g. a rebase changed
 * its SHA and the thread couldn't be auto-reattached). Surfaced so the human
 * can still read and resolve them. Renders nothing when there are none.
 */
export function OrphanThreads() {
  const { data } = useQuery({
    queryKey: ["threads", "orphans"],
    queryFn: api.orphanThreads,
    refetchInterval: 5000,
  });
  const [open, setOpen] = useState(true);

  const orphans = (data ?? []).filter((t) => t.status === "open");
  if (orphans.length === 0) return null;

  return (
    <section className="mb-4 rounded border border-amber-400 dark:border-amber-700/70 bg-amber-50 dark:bg-amber-950/30">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-left"
      >
        <span className="text-sm font-medium text-amber-800 dark:text-amber-300">
          ⚠ {orphans.length} unattached thread{orphans.length > 1 ? "s" : ""}
        </span>
        <span className="text-xs text-amber-700 dark:text-amber-400">
          {open ? "hide" : "show"}
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-3">
          <p className="text-xs text-amber-700 dark:text-amber-400">
            The commit these threads were left on is no longer in history (likely
            rebased). They couldn't be auto-reattached. Read and resolve them here.
          </p>
          {orphans.map((t) => (
            <div key={t.id}>
              <div className="text-xs text-zinc-500 mb-1 font-mono">
                {t.file_path}:{t.line_number} · was {t.commit_sha.slice(0, 7)}
              </div>
              <ThreadView thread={t} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
