import type { FileDiff, Thread } from "../api/types";

/**
 * Threads anchored to a file that isn't present in the commit's current diff
 * (e.g. the file was deleted, or added-then-deleted so it nets out of the
 * comparison). They can't render inline against any file, so the caller shows
 * them separately. Threads whose file *is* shown — even on a line that's gone —
 * are handled inline by FileDiff and are not returned here.
 */
export function detachedThreads(files: FileDiff[], threads: Thread[]): Thread[] {
  const shown = new Set(files.map((f) => f.new_path ?? f.old_path ?? ""));
  return threads.filter((t) => !shown.has(t.file_path));
}
