import { useState } from "react";
import type { Thread } from "../api/types";

interface Props {
  threads: Thread[];
}

function scrollToThread(id: number) {
  const el = document.getElementById(`gitloco-thread-${id}`);
  if (!el) return; // thread's file may be collapsed — nothing to scroll to
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  // Brief highlight so the eye lands on it (plain CSS class — see diff.css).
  el.classList.add("gitloco-flash");
  window.setTimeout(() => el.classList.remove("gitloco-flash"), 1400);
}

function basename(path: string): string {
  const i = path.lastIndexOf("/");
  return i >= 0 ? path.slice(i + 1) : path;
}

function ThreadItem({ thread, onPick }: { thread: Thread; onPick: () => void }) {
  return (
    <button
      type="button"
      onClick={onPick}
      className="w-full text-left px-3 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800/60"
    >
      <div className="flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400 font-mono truncate">
        <span className="truncate">{basename(thread.file_path)}</span>
        <span className="shrink-0">:{thread.line_number}</span>
      </div>
      <div className="text-xs text-zinc-800 dark:text-zinc-200 line-clamp-2">
        {thread.replies[0]?.body ?? "(no message)"}
      </div>
    </button>
  );
}

/**
 * An index of the open threads on the current commit, like a minimap. Clicking
 * an entry scrolls its inline thread into view. Hidden when there are no open
 * threads. On wide screens it's a sticky right sidebar; on narrow screens it
 * becomes a bottom sheet that expands upward.
 */
export function ThreadMinimap({ threads }: Props) {
  const [open, setOpen] = useState(false);
  if (threads.length === 0) return null;

  return (
    <>
      {/* Wide screens: sticky right sidebar */}
      <aside className="hidden lg:block w-64 shrink-0">
        <div className="sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto rounded border border-zinc-200 dark:border-zinc-800">
          <div className="px-3 py-2 border-b border-zinc-200 dark:border-zinc-800 text-xs font-medium text-zinc-600 dark:text-zinc-300">
            Open threads ({threads.length})
          </div>
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800/70">
            {threads.map((t) => (
              <li key={t.id}>
                <ThreadItem thread={t} onPick={() => scrollToThread(t.id)} />
              </li>
            ))}
          </ul>
        </div>
      </aside>

      {/* Narrow screens: fixed bottom sheet */}
      <div className="lg:hidden fixed inset-x-0 bottom-0 z-30 border-t border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 shadow-[0_-4px_12px_rgba(0,0,0,0.08)]">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="w-full flex items-center justify-between px-4 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-200"
        >
          <span>Open threads ({threads.length})</span>
          <svg
            width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden
            className={["transition-transform", open ? "rotate-180" : ""].join(" ")}
          >
            <path d="M3 10l5-5 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {open && (
          <ul className="max-h-[45vh] overflow-y-auto divide-y divide-zinc-100 dark:divide-zinc-800/70 border-t border-zinc-200 dark:border-zinc-800">
            {threads.map((t) => (
              <li key={t.id}>
                <ThreadItem
                  thread={t}
                  onPick={() => {
                    setOpen(false);
                    scrollToThread(t.id);
                  }}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
