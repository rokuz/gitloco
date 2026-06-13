import type {
  CommitDiff,
  CommitList,
  CommitVersion,
  CompareOut,
  NewThreadIn,
  Thread,
  ThreadStatus,
} from "./types";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`);
  return res.json() as Promise<T>;
}

async function sendJson<T>(
  method: "POST" | "PUT" | "PATCH",
  url: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} — ${url}\n${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () =>
    getJson<{ status: string; version: string; repo: string; repo_path: string }>(
      "/api/health",
    ),
  commits: () => getJson<CommitList>("/api/commits"),
  diff: (sha: string) => getJson<CommitDiff>(`/api/commits/${encodeURIComponent(sha)}/diff`),
  threads: (params: { sha?: string; path?: string; status?: ThreadStatus | "all" } = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.sha) qs.set("sha", params.sha);
    if (params.path) qs.set("path", params.path);
    const query = qs.toString();
    return getJson<Thread[]>(`/api/threads${query ? `?${query}` : ""}`);
  },
  orphanThreads: () => getJson<Thread[]>("/api/threads/orphans"),
  openThreadCounts: () => getJson<Record<string, number>>("/api/threads/open-counts"),
  createThread: (input: NewThreadIn) => sendJson<Thread>("POST", "/api/threads", input),
  replyToThread: (threadId: number, body: string) =>
    sendJson<Thread>("POST", `/api/threads/${threadId}/replies`, { body }),
  resolveThread: (threadId: number) =>
    sendJson<Thread>("POST", `/api/threads/${threadId}/resolve`),
  commitVersions: (sha: string) =>
    getJson<CommitVersion[]>(`/api/commits/${encodeURIComponent(sha)}/versions`),
  commitCompare: (sha: string, fromName: string, toName: string) => {
    const qs = new URLSearchParams({ from: fromName, to: toName });
    return getJson<CompareOut>(
      `/api/commits/${encodeURIComponent(sha)}/compare?${qs}`,
    );
  },
};
