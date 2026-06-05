import type { CommitVersion } from "../api/types";

interface Props {
  versions: CommitVersion[];
  fromName: string;
  toName: string;
  onChange: (next: { fromName: string; toName: string }) => void;
}

function versionLabel(v: CommitVersion): string {
  return `V${v.version_number} · ${v.short_hash}`;
}

export function parseVersion(name: string): number | null {
  if (!name.toLowerCase().startsWith("v")) return null;
  const n = parseInt(name.slice(1), 10);
  return Number.isFinite(n) ? n : null;
}

/** Numeric position of a from/to selection: "base" sits before V1 (0),
 *  "latest" maps to the latest version number. */
export function refNumber(name: string, latestNumber: number): number | null {
  if (name === "base") return 0;
  if (name === "latest") return latestNumber;
  return parseVersion(name);
}

/** Versions selectable as the "from" baseline — any except the latest, since
 *  nothing comes after the latest to compare forward to. ("base" is added
 *  separately in the markup.) */
export function fromOptions(
  versions: CommitVersion[],
  latestNumber: number,
): CommitVersion[] {
  return versions.filter((v) => v.version_number < latestNumber);
}

/** Versions selectable as "to" — only those strictly after the chosen "from",
 *  so a comparison always reads forward in time (no V2 → V1). */
export function toOptions(
  versions: CommitVersion[],
  fromName: string,
): CommitVersion[] {
  const fromNumber = fromName === "base" ? 0 : (parseVersion(fromName) ?? 0);
  return versions.filter((v) => v.version_number > fromNumber);
}

/** When "from" changes, keep "to" valid: if it's no longer strictly after
 *  "from", snap to "latest" (always valid because "from" is never the latest). */
export function reconcileTo(
  fromName: string,
  toName: string,
  latestNumber: number,
): string {
  const fromNumber = fromName === "base" ? 0 : (parseVersion(fromName) ?? 0);
  const toNum = refNumber(toName, latestNumber);
  return toNum !== null && toNum > fromNumber ? toName : "latest";
}

export function VersionPicker({ versions, fromName, toName, onChange }: Props) {
  if (versions.length === 0) return null;
  const latestNumber = versions[versions.length - 1].version_number;
  const froms = fromOptions(versions, latestNumber);
  const tos = toOptions(versions, fromName);
  const toResolvedNumber = refNumber(toName, latestNumber);

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-zinc-600 dark:text-zinc-400">Compare</span>
      <select
        value={fromName}
        onChange={(e) =>
          onChange({
            fromName: e.target.value,
            toName: reconcileTo(e.target.value, toName, latestNumber),
          })
        }
        className="rounded border border-zinc-300 bg-white text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 px-2 py-1"
      >
        <option value="base">Base (commit's parent)</option>
        {froms.map((v) => (
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
        {tos.map((v) => (
          <option key={v.version_number} value={`V${v.version_number}`}>
            {versionLabel(v)}
            {v.version_number === latestNumber ? " (latest)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
