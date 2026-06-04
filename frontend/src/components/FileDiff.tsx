import { useMemo } from "react";
import {
  Diff,
  Hunk,
  getChangeKey,
  isDelete,
  isInsert,
  isNormal,
  parseDiff,
  tokenize,
} from "react-diff-view";
import type { ChangeData, HunkData, HunkTokens } from "react-diff-view";
import { refractor } from "refractor";
import tsxLang from "refractor/tsx";
import jsxLang from "refractor/jsx";

// Register languages the common bundle doesn't ship.
refractor.register(tsxLang);
refractor.register(jsxLang);

// react-diff-view 3.x expects refractor's old highlight shape (array of HAST
// nodes), but refractor v5 wraps them in a Root node. Adapt by peeling off
// the root.
const refractorAdapter = {
  highlight(text: string, language: string): unknown[] {
    const root = refractor.highlight(text, language) as {
      children?: unknown[];
    };
    return root?.children ?? [];
  },
};
import type { FileDiff as FileDiffData, LineSide, Thread } from "../api/types";
import { detectLanguage } from "../utils/language";
import { NewThreadComposer } from "./NewThreadComposer";
import { ThreadView } from "./ThreadView";

interface Props {
  file: FileDiffData;
  commitSha: string;
  threads: Thread[];
  composer: { side: LineSide; line: number } | null;
  onOpenComposer: (side: LineSide, line: number) => void;
  onCloseComposer: () => void;
}

const STATUS_LABEL: Record<FileDiffData["status"], string> = {
  added: "added",
  deleted: "deleted",
  modified: "modified",
  renamed: "renamed",
  copied: "copied",
};

const STATUS_COLOR: Record<FileDiffData["status"], string> = {
  added: "bg-emerald-900/40 text-emerald-300",
  deleted: "bg-rose-900/40 text-rose-300",
  modified: "bg-amber-900/40 text-amber-300",
  renamed: "bg-sky-900/40 text-sky-300",
  copied: "bg-sky-900/40 text-sky-300",
};

function findChangeKey(
  hunks: HunkData[],
  side: LineSide,
  lineNumber: number,
): string | undefined {
  for (const h of hunks) {
    for (const change of h.changes) {
      if (isNormal(change)) {
        if (side === "new" && change.newLineNumber === lineNumber) return getChangeKey(change);
        if (side === "old" && change.oldLineNumber === lineNumber) return getChangeKey(change);
      } else if (isInsert(change) && side === "new" && change.lineNumber === lineNumber) {
        return getChangeKey(change);
      } else if (isDelete(change) && side === "old" && change.lineNumber === lineNumber) {
        return getChangeKey(change);
      }
    }
  }
  return undefined;
}

function changeToLine(change: ChangeData): { side: LineSide; line: number } | null {
  if (isInsert(change)) return { side: "new", line: change.lineNumber };
  if (isDelete(change)) return { side: "old", line: change.lineNumber };
  if (isNormal(change)) return { side: "new", line: change.newLineNumber };
  return null;
}

export function FileDiff({
  file,
  commitSha,
  threads,
  composer,
  onOpenComposer,
  onCloseComposer,
}: Props) {
  const displayPath =
    file.new_path && file.new_path !== "/dev/null"
      ? file.new_path
      : file.old_path ?? "(unknown)";

  if (file.is_binary) {
    return (
      <section className="rounded border border-zinc-800 overflow-hidden">
        <FileHeader file={file} displayPath={displayPath} />
        <div className="bg-zinc-950 px-4 py-3 text-sm text-zinc-400">Binary file</div>
      </section>
    );
  }

  const parsed = parseDiff(file.patch_text);
  if (parsed.length === 0) {
    return (
      <section className="rounded border border-zinc-800 overflow-hidden">
        <FileHeader file={file} displayPath={displayPath} />
        <div className="bg-zinc-950 px-4 py-3 text-sm text-zinc-400">No textual changes.</div>
      </section>
    );
  }

  const language = detectLanguage(file.new_path ?? file.old_path);
  const filePath = file.new_path ?? file.old_path ?? "";

  return (
    <section className="rounded border border-zinc-800 overflow-hidden">
      <FileHeader file={file} displayPath={displayPath} />
      {parsed.map((parsedFile, fIdx) => (
        <ParsedFileBody
          key={fIdx}
          parsedFile={parsedFile}
          language={language}
          filePath={filePath}
          commitSha={commitSha}
          threads={threads}
          composer={composer}
          onOpenComposer={onOpenComposer}
          onCloseComposer={onCloseComposer}
        />
      ))}
    </section>
  );
}

interface ParsedFileBodyProps {
  parsedFile: { type: FileDiffData["status"] | "add" | "delete" | "modify" | "rename" | "copy"; hunks: HunkData[] };
  language: string | null;
  filePath: string;
  commitSha: string;
  threads: Thread[];
  composer: { side: LineSide; line: number } | null;
  onOpenComposer: (side: LineSide, line: number) => void;
  onCloseComposer: () => void;
}

function ParsedFileBody({
  parsedFile,
  language,
  filePath,
  commitSha,
  threads,
  composer,
  onOpenComposer,
  onCloseComposer,
}: ParsedFileBodyProps) {
  const tokens = useMemo<HunkTokens | undefined>(() => {
    if (!language) return undefined;
    try {
      return tokenize(parsedFile.hunks, {
        highlight: true,
        refractor: refractorAdapter as Parameters<
          typeof tokenize
        >[1] extends { refractor: infer R }
          ? R
          : never,
        language,
      } as Parameters<typeof tokenize>[1]);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("tokenize failed for", language, e);
      return undefined;
    }
  }, [parsedFile.hunks, language]);

  const widgets: Record<string, React.ReactNode> = {};

  for (const t of threads) {
    const key = findChangeKey(parsedFile.hunks, t.line_side, t.line_number);
    if (!key) continue;
    const existing = widgets[key];
    widgets[key] = (
      <>
        {existing}
        <ThreadView thread={t} />
      </>
    );
  }

  if (composer) {
    const key = findChangeKey(parsedFile.hunks, composer.side, composer.line);
    if (key) {
      const existing = widgets[key];
      widgets[key] = (
        <>
          {existing}
          <NewThreadComposer
            commitSha={commitSha}
            filePath={filePath}
            lineSide={composer.side}
            lineNumber={composer.line}
            onCancel={onCloseComposer}
            onCreated={onCloseComposer}
          />
        </>
      );
    }
  }

  return (
    <Diff
      viewType="unified"
      diffType={parsedFile.type as never}
      hunks={parsedFile.hunks}
      widgets={widgets}
      tokens={tokens}
      gutterEvents={{
        onClick: ({ change }) => {
          if (!change) return;
          const target = changeToLine(change);
          if (!target) return;
          onOpenComposer(target.side, target.line);
        },
      }}
    >
      {(hunks) => hunks.map((hunk) => <Hunk key={hunk.content} hunk={hunk} />)}
    </Diff>
  );
}

function FileHeader({
  file,
  displayPath,
}: {
  file: FileDiffData;
  displayPath: string;
}) {
  const renamed =
    file.status === "renamed" && file.old_path && file.old_path !== file.new_path;
  return (
    <header className="flex items-center gap-2 bg-zinc-900 px-3 py-2 border-b border-zinc-800">
      <span
        className={[
          "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
          STATUS_COLOR[file.status],
        ].join(" ")}
      >
        {STATUS_LABEL[file.status]}
      </span>
      <code className="font-mono text-xs text-zinc-200 truncate">
        {renamed ? `${file.old_path} → ${displayPath}` : displayPath}
      </code>
    </header>
  );
}
