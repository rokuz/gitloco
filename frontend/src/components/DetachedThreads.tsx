import type { Thread } from "../api/types";
import { ThreadView } from "./ThreadView";

/**
 * Threads left on a file that no longer appears in this commit's diff (e.g. the
 * file was deleted), so they can't render inline. Shown at the end of the page
 * so they stay visible and resolvable. Renders nothing when there are none.
 */
export function DetachedThreads({ threads }: { threads: Thread[] }) {
  if (threads.length === 0) return null;
  return (
    <section className="rounded border border-amber-400 dark:border-amber-700/70 bg-amber-50 dark:bg-amber-950/30">
      <div className="px-3 py-2 text-sm font-medium text-amber-800 dark:text-amber-300">
        💬 {threads.length} comment{threads.length > 1 ? "s" : ""} on a removed file
      </div>
      <div className="px-3 pb-3 space-y-3">
        <p className="text-xs text-amber-700 dark:text-amber-400">
          These threads were left on a file that's no longer in this diff (e.g.
          it was deleted). Read and resolve them here.
        </p>
        {threads.map((t) => (
          <div key={t.id}>
            <div className="text-xs text-zinc-500 mb-1 font-mono">
              {t.file_path}:{t.line_number}
            </div>
            <ThreadView thread={t} />
          </div>
        ))}
      </div>
    </section>
  );
}
