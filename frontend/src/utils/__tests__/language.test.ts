import { describe, expect, it } from "vitest";
import { detectLanguage } from "../language";

describe("detectLanguage", () => {
  it.each([
    ["src/foo.ts", "typescript"],
    ["src/App.tsx", "tsx"],
    ["src/main.jsx", "jsx"],
    ["lib/util.py", "python"],
    ["lib/util.pyi", "python"],
    ["main.cpp", "cpp"],
    ["main.cxx", "cpp"],
    ["main.hh", "cpp"],
    ["main.c", "c"],
    ["a.go", "go"],
    ["a.rs", "rust"],
    ["build.toml", "toml"],
    ["Dockerfile", "docker"],
    ["Makefile", "makefile"],
  ])("maps %s → %s", (path, lang) => {
    expect(detectLanguage(path)).toBe(lang);
  });

  it("returns null for unknown extensions", () => {
    expect(detectLanguage("notes.unknown")).toBeNull();
    expect(detectLanguage("nofile")).toBeNull();
  });

  it("handles null / undefined input", () => {
    expect(detectLanguage(null)).toBeNull();
    expect(detectLanguage(undefined)).toBeNull();
    expect(detectLanguage("")).toBeNull();
  });

  it("is case-insensitive on extension", () => {
    expect(detectLanguage("Foo.TS")).toBe("typescript");
    expect(detectLanguage("Foo.PY")).toBe("python");
  });
});
