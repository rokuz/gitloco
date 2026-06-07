import { describe, expect, it } from "vitest";

import type { FileDiff, Thread } from "../../api/types";
import { detachedThreads } from "../detachedThreads";

function file(path: string, status: FileDiff["status"] = "modified"): FileDiff {
  return {
    old_path: path,
    new_path: status === "deleted" ? null : path,
    status,
    is_binary: false,
    patch_text: "",
  };
}

function thread(id: number, file_path: string): Thread {
  return {
    id,
    commit_sha: "abc",
    file_path,
    line_side: "new",
    line_number: 1,
    status: "open",
    created_at: "2026-01-01",
    resolved_at: null,
    replies: [],
  };
}

describe("detachedThreads", () => {
  it("returns threads whose file is absent from the diff", () => {
    const files = [file("a.py"), file("b.py")];
    const threads = [thread(1, "a.py"), thread(2, "gone.py")];
    expect(detachedThreads(files, threads).map((t) => t.id)).toEqual([2]);
  });

  it("keeps threads on a shown file (even a deleted one) inline (not detached)", () => {
    const files = [file("old.py", "deleted")]; // old_path set, new_path null
    expect(detachedThreads(files, [thread(1, "old.py")])).toEqual([]);
  });

  it("when nothing is shown, all threads are detached", () => {
    expect(
      detachedThreads([], [thread(1, "a.py"), thread(2, "b.py")]).map((t) => t.id),
    ).toEqual([1, 2]);
  });

  it("no detached threads when every file is present", () => {
    expect(detachedThreads([file("a.py")], [thread(1, "a.py")])).toEqual([]);
  });
});
