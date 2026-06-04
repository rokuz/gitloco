import type { CommitVersion } from "../api/types";

interface Props {
  versions: CommitVersion[];
  fromName: string;
  toName: string;
  onChange: (next: { fromName: string; toName: string }) => void;
}

function versionLabel(v: CommitVersion): string {
  const time = new Date(v.created_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  const kind =
    v.trigger === "thread_created"
      ? "initial"
      : v.trigger === "rewrite"
        ? "fix"
        : "edit";
  return `V${v.version_number} · ${kind} · ${time}`;
}

export function VersionPicker({ versions, fromName, toName, onChange }: Props) {
  if (versions.length === 0) return null;
  const latestNumber = versions[versions.length - 1].version_number;
  const toResolvedNumber =
    toName === "latest" ? latestNumber : tryParseVersion(toName);

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-zinc-600 dark:text-zinc-400">Compare</span>
      <select
        value={fromName}
        onChange={(e) => onChange({ fromName: e.target.value, toName })}
        className="rounded border border-zinc-300 bg-white text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 px-2 py-1"
      >
        <option value="base">Base (commit's parent)</option>
        {versions.map((v) => (
          <option key={v.version_number} value={`V${v.version_number}`}>
            {versionLabel(v)}
          </option>
        ))}
      </select>
      <span className="text-zinc-500">→</span>
      <select
        value={toName === "latest" && toResolvedNumber !== null ? `V${toResolvedNumber}` : toName}
        onChange={(e) => onChange({ fromName, toName: e.target.value })}
        className="rounded border border-zinc-300 bg-white text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 px-2 py-1"
      >
        {versions.map((v) => (
          <option key={v.version_number} value={`V${v.version_number}`}>
            {versionLabel(v)}
            {v.version_number === latestNumber ? " (latest)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

function tryParseVersion(name: string): number | null {
  if (!name.toLowerCase().startsWith("v")) return null;
  const n = parseInt(name.slice(1), 10);
  return Number.isFinite(n) ? n : null;
}
