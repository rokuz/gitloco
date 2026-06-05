import { describe, expect, it } from "vitest";

import type { CommitVersion } from "../../api/types";
import { fromOptions, reconcileTo, toOptions } from "../VersionPicker";

function v(n: number): CommitVersion {
  return {
    version_number: n,
    commit_hash: `hash${n}`,
    short_hash: `h${n}`,
    subject: `s${n}`,
    created_at: "2026-01-01",
  };
}

const versions = [v(1), v(2), v(3)]; // latest = 3

describe("VersionPicker option constraints", () => {
  it("from excludes the latest version (nothing comes after it)", () => {
    expect(fromOptions(versions, 3).map((x) => x.version_number)).toEqual([1, 2]);
  });

  it("to only offers versions strictly after from", () => {
    expect(toOptions(versions, "base").map((x) => x.version_number)).toEqual([1, 2, 3]);
    expect(toOptions(versions, "V1").map((x) => x.version_number)).toEqual([2, 3]);
    expect(toOptions(versions, "V2").map((x) => x.version_number)).toEqual([3]);
  });

  it("never offers a backwards comparison (V2 -> V1 is impossible)", () => {
    expect(toOptions(versions, "V2").map((x) => x.version_number)).not.toContain(1);
  });

  it("single version: from is base-only, to is V1", () => {
    expect(fromOptions([v(1)], 1)).toEqual([]);
    expect(toOptions([v(1)], "base").map((x) => x.version_number)).toEqual([1]);
  });

  it("reconcileTo keeps a still-valid to, snaps an invalid one to latest", () => {
    // to=V3 stays valid when from becomes V2
    expect(reconcileTo("V2", "V3", 3)).toBe("V3");
    // to=V1 is now <= from=V2 -> snap to latest
    expect(reconcileTo("V2", "V1", 3)).toBe("latest");
    // "latest" is always valid
    expect(reconcileTo("V2", "latest", 3)).toBe("latest");
  });
});
