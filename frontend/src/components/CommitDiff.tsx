import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  CompareFile,
  FileDiff as FileDiffData,
  LineSide,
} from "../api/types";
import { FileDiff } from "./FileDiff";
import { ThreadMinimap } from "./ThreadMinimap";
import { VersionPicker } from "./VersionPicker";

interface Props {
  sha: string;
}

interface ComposerState {
  filePath: string;
  side: LineSide;
  line: number;
}

function compareFileToDiff(c: CompareFile): FileDiffData {
  // Map CompareFile.status → FileDiffData.status. Binary is reported via
  // is_binary; we pick "modified" as the umbrella status so the existing
  // FileDiff component renders its binary placeholder cleanly.
  const mapped =
    c.status === "binary" || c.status === "unchanged"
      ? "modified"
      : c.status;
  return {
    old_path: c.old_path,
    new_path: c.new_path,
    status: mapped,
    is_binary: c.is_binary,
    patch_text: c.patch_text,
  };
}

export function CommitDiff({ sha }: Props) {
  const versionsQuery = useQuery({
    queryKey: ["versions", sha],
    queryFn: () => api.commitVersions(sha),
    refetchInterval: 5000,
  });
  const hasVersions = (versionsQuery.data?.length ?? 0) > 0;

  const [fromName, setFromName] = useState("base");
  const [toName, setToName] = useState("latest");

  // Reset picker when switching commits.
  useEffect(() => {
    setFromName("base");
    setToName("latest");
  }, [sha]);

  const compareQuery = useQuery({
    queryKey: ["compare", sha, fromName, toName],
    queryFn: () => api.commitCompare(sha, fromName, toName),
    enabled: hasVersions,
  });

  const liveDiffQuery = useQuery({
    queryKey: ["diff", sha],
    queryFn: () => api.diff(sha),
    enabled: !hasVersions,
  });

  const threadsQuery = useQuery({
    queryKey: ["threads", { sha, status: "all" }],
    queryFn: () => api.threads({ sha, status: "all" }),
    refetchInterval: 5000,
  });

  const [composer, setComposer] = useState<ComposerState | null>(null);
  const [showLatestPrompt, setShowLatestPrompt] = useState(false);

  // Comments anchor to the commit's current (latest) content, so they may only
  // be left while viewing the latest version. When older versions are being
  // compared, a gutter click prompts the user to switch to latest instead.
  const latestNumber = versionsQuery.data?.length
    ? Math.max(...versionsQuery.data.map((v) => v.version_number))
    : 0;
  const toNumber =
    toName === "latest" ? latestNumber : parseInt(toName.replace(/^[vV]/, ""), 10);
  const canComment = !hasVersions || toNumber === latestNumber;

  const switchToLatest = () => {
    setFromName("base");
    setToName("latest");
    setShowLatestPrompt(false);
  };

  const isLoading =
    versionsQuery.isLoading ||
    (hasVersions ? compareQuery.isLoading : liveDiffQuery.isLoading);
  const error =
    versionsQuery.error ??
    (hasVersions ? compareQuery.error : liveDiffQuery.error);

  if (isLoading) return <div className="p-4 text-sm text-zinc-600 dark:text-zinc-400">Loading diff…</div>;
  if (error) return <div className="p-4 text-sm text-red-600 dark:text-red-400">Error: {String(error)}</div>;

  const files: FileDiffData[] = hasVersions
    ? (compareQuery.data?.files ?? [])
        .filter((c) => c.status !== "unchanged")
        .map(compareFileToDiff)
    : (liveDiffQuery.data?.files ?? []);

  const threads = threadsQuery.data ?? [];
  const openThreads = threads
    .filter((t) => t.status === "open")
    .sort((a, b) =>
      a.file_path === b.file_path
        ? a.line_number - b.line_number
        : a.file_path.localeCompare(b.file_path),
    );

  return (
    <div className="flex gap-4">
      <div className="flex-1 min-w-0 space-y-4">
        {hasVersions && versionsQuery.data && (
          <VersionPicker
            versions={versionsQuery.data}
            fromName={fromName}
            toName={toName}
            onChange={({ fromName, toName }) => {
              setFromName(fromName);
              setToName(toName);
            }}
          />
        )}
        {files.length === 0 ? (
          <div className="p-4 text-sm text-zinc-600 dark:text-zinc-400">No changes.</div>
        ) : (
          files.map((f) => {
            const filePath = f.new_path ?? f.old_path ?? "";
            const fileThreads = threads.filter((t) => t.file_path === filePath);
            const fileComposer =
              composer && composer.filePath === filePath
                ? { side: composer.side, line: composer.line }
                : null;
            return (
              <FileDiff
                key={filePath + "::" + f.status}
                file={f}
                commitSha={sha}
                threads={fileThreads}
                composer={fileComposer}
                onOpenComposer={(side, line) => {
                  if (!canComment) {
                    setShowLatestPrompt(true);
                    return;
                  }
                  setComposer({ filePath, side, line });
                }}
                onCloseComposer={() => setComposer(null)}
              />
            );
          })
        )}
      </div>
      <ThreadMinimap threads={openThreads} />

      {showLatestPrompt && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setShowLatestPrompt(false)}
        >
          <div
            className="mx-4 max-w-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Comments go on the latest version
            </h3>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
              You're viewing an older version. Switch to the latest version to
              leave a comment.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowLatestPrompt(false)}
                className="px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={switchToLatest}
                className="rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-50 dark:bg-zinc-700 dark:hover:bg-zinc-600 px-3 py-1.5 text-sm"
              >
                Switch to latest
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
