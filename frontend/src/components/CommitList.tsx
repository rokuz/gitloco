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

  if (isLoading) return <div className="p-4 text-sm text-zinc-600 dark:text-zinc-400">Loading commits…</div>;
  if (error) return <div className="p-4 text-sm text-red-600 dark:text-red-400">Error: {String(error)}</div>;
  if (!data || data.commits.length === 0) {
    return <div className="p-4 text-sm text-zinc-600 dark:text-zinc-400">No commits yet.</div>;
  }

  return (
    <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
      {data.commits.map((c) => (
        <CommitRow
          key={c.sha}
          commit={c}
          selected={c.sha === selectedSha}
          onClick={() => onSelect(c.sha)}
        />
      ))}
    </ul>
  );
}

function CommitRow({
  commit,
  selected,
  onClick,
}: {
  commit: Commit;
  selected: boolean;
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
