// Map a file path → refractor language name (or null if we can't guess).
// Only languages bundled in refractor's "common" entry need to be supported here;
// others gracefully fall through to no highlighting.

const BY_EXT: Record<string, string> = {
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  rb: "ruby",
  go: "go",
  rs: "rust",
  java: "java",
  kt: "kotlin",
  kts: "kotlin",
  c: "c",
  h: "c",
  cpp: "cpp",
  cc: "cpp",
  hpp: "cpp",
  cs: "csharp",
  swift: "swift",
  php: "php",
  scala: "scala",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  yml: "yaml",
  yaml: "yaml",
  json: "json",
  toml: "toml",
  md: "markdown",
  markdown: "markdown",
  html: "markup",
  htm: "markup",
  xml: "markup",
  svg: "markup",
  css: "css",
  scss: "scss",
  sql: "sql",
  ini: "ini",
  diff: "diff",
};

const BY_FILENAME: Record<string, string> = {
  Dockerfile: "docker",
  Makefile: "makefile",
};

export function detectLanguage(filePath: string | null | undefined): string | null {
  if (!filePath) return null;
  const slash = filePath.lastIndexOf("/");
  const base = slash >= 0 ? filePath.slice(slash + 1) : filePath;
  if (BY_FILENAME[base]) return BY_FILENAME[base];
  const dot = base.lastIndexOf(".");
  if (dot < 0) return null;
  const ext = base.slice(dot + 1).toLowerCase();
  return BY_EXT[ext] ?? null;
}
