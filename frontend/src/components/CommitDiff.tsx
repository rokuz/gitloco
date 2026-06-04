import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  CompareFile,
  FileDiff as FileDiffData,
  LineSide,
} from "../api/types";
import { FileDiff } from "./FileDiff";
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

  return (
    <div className="space-y-4">
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
              onOpenComposer={(side, line) =>
                setComposer({ filePath, side, line })
              }
              onCloseComposer={() => setComposer(null)}
            />
          );
        })
      )}
    </div>
  );
}
