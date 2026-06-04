import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Commit } from "../api/types";

interface Props {
  selectedSha: string | null;
  onSelect: (sha: string) => void;
}

export function CommitList({ selectedSha, onSelect }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["commits"],
    queryFn: api.commits,
    refetchInterval: 5000,
  });
  const { data: openCounts } = useQuery({
    queryKey: ["threads", "open-counts"],
    queryFn: api.openThreadCounts,
    refetchInterval: 5000,
  });

  if (isLoading) return <div className="p-4 text-sm text-zinc-600 dark:text-zinc-400">Loading commits…</div>;
  if (error) return <div className="p-4 text-sm text-red-600 dark:text-red-400">Error: {String(error)}</div>;
  if (!data || data.commits.length === 0) {
    return <div className="p-4 text-sm text-zinc-600 dark:text-zinc-400">No commits yet.</div>;
  }

  return (
    <div>
      {data.branch && (
        <div className="flex items-center gap-1.5 px-3 py-2 border-b border-zinc-200 dark:border-zinc-800 text-xs text-zinc-600 dark:text-zinc-400">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor" aria-hidden className="shrink-0 text-zinc-500">
            <path d="M11.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5zm-2.25.75a2.25 2.25 0 1 1 3 2.122V6A2.5 2.5 0 0 1 10 8.5H6a1 1 0 0 0-1 1v1.128a2.251 2.251 0 1 1-1.5 0V5.372a2.25 2.25 0 1 1 1.5 0v1.836A2.493 2.493 0 0 1 6 7h4a1 1 0 0 0 1-1v-.628A2.25 2.25 0 0 1 9.5 3.25zM4.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5zM3.5 3.25a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0z" />
          </svg>
          <span className="font-mono truncate" title={`On branch ${data.branch}`}>
            {data.branch}
          </span>
        </div>
      )}
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {data.commits.map((c) => (
          <CommitRow
            key={c.sha}
            commit={c}
            selected={c.sha === selectedSha}
            openCount={openCounts?.[c.sha] ?? 0}
            onClick={() => onSelect(c.sha)}
          />
        ))}
      </ul>
    </div>
  );
}

function CommitRow({
  commit,
  selected,
  openCount,
  onClick,
}: {
  commit: Commit;
  selected: boolean;
  openCount: number;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={[
          "w-full text-left px-3 py-3 md:py-2 transition-colors",
          selected
            ? "bg-zinc-200 dark:bg-zinc-800"
            : "hover:bg-zinc-100 active:bg-zinc-200 dark:hover:bg-zinc-900 dark:active:bg-zinc-800",
        ].join(" ")}
      >
        <div className="flex items-center gap-2">
          <span
            className={[
              "inline-block h-2 w-2 rounded-full shrink-0",
              commit.is_working_tree
                ? "bg-amber-500 dark:bg-amber-400"
                : "bg-zinc-400 dark:bg-zinc-500",
            ].join(" ")}
            aria-hidden
          />
          <span className="font-mono text-xs text-zinc-600 dark:text-zinc-400 shrink-0">
            {commit.short_sha}
          </span>
          <span className="truncate text-sm text-zinc-900 dark:text-zinc-100">
            {commit.subject}
          </span>
          {openCount > 0 && (
            <span
              title={`${openCount} unresolved thread${openCount > 1 ? "s" : ""}`}
              className="ml-auto shrink-0 inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300 px-1.5 py-0.5 text-[10px] font-medium"
            >
              <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
                <path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H6l-3 3v-3H3a1 1 0 0 1-1-1V3z" />
              </svg>
              {openCount}
            </span>
          )}
        </div>
        <div className="ml-4 pl-2 text-xs text-zinc-500 truncate">
          {commit.is_working_tree
            ? "—"
            : `${commit.author_name} · ${relativeTime(commit.committed_at)}`}
        </div>
      </button>
    </li>
  );
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffMs = now - then;
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  return new Date(iso).toLocaleDateString();
}
