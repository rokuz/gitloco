import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import type { Reply, Thread } from "../api/types";

interface Props {
  thread: Thread;
}

export function ThreadView({ thread }: Props) {
  const qc = useQueryClient();
  const [replyBody, setReplyBody] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["threads"] });

  const replyMutation = useMutation({
    mutationFn: (body: string) => api.replyToThread(thread.id, body),
    onSuccess: () => {
      setReplyBody("");
      invalidate();
    },
  });

  const resolveMutation = useMutation({
    mutationFn: () => api.resolveThread(thread.id),
    onSuccess: invalidate,
  });

  const isResolved = thread.status === "resolved";
  // Resolved threads start collapsed (they're done); open ones start expanded.
  const [collapsed, setCollapsed] = useState(isResolved);

  const firstMessage = thread.replies[0]?.body ?? "";

  return (
    <div className="my-2 rounded border border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 text-sm">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
        title={collapsed ? "Expand thread" : "Collapse thread"}
        className="flex w-full items-center gap-2 px-3 py-1.5 border-b border-zinc-200 dark:border-zinc-800 text-xs text-left hover:bg-zinc-100 dark:hover:bg-zinc-800"
      >
        <svg
          width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden
          className={["shrink-0 text-zinc-700 dark:text-zinc-300 transition-transform", collapsed ? "-rotate-90" : ""].join(" ")}
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="shrink-0 text-zinc-600 dark:text-zinc-400">
          Thread #{thread.id} ·{" "}
          <span
            className={
              isResolved
                ? "text-emerald-700 dark:text-emerald-400"
                : "text-amber-700 dark:text-amber-400"
            }
          >
            {isResolved ? "resolved" : "open"}
          </span>
        </span>
        {collapsed && (
          <span className="ml-2 truncate text-zinc-500 dark:text-zinc-500">
            {firstMessage}
            {thread.replies.length > 1 ? ` · ${thread.replies.length} messages` : ""}
          </span>
        )}
      </button>
      {!collapsed && (
        <>
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {thread.replies.map((r) => (
          <ReplyRow key={r.id} reply={r} />
        ))}
      </ul>
      {!isResolved && (
        <div className="border-t border-zinc-200 dark:border-zinc-800 p-2 space-y-2">
          <textarea
            value={replyBody}
            onChange={(e) => setReplyBody(e.target.value)}
            placeholder="Reply…"
            rows={2}
            className="w-full resize-y rounded border border-zinc-300 bg-white text-zinc-900 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100 px-2 py-1 text-sm focus:outline-none focus:border-zinc-500 dark:focus:border-zinc-500"
          />
          {replyMutation.error && (
            <div className="text-xs text-red-600 dark:text-red-400">{String(replyMutation.error)}</div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => resolveMutation.mutate()}
              disabled={resolveMutation.isPending}
              className="inline-flex items-center gap-1 rounded border border-emerald-600 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-500 dark:text-emerald-300 dark:hover:bg-emerald-950/40 disabled:opacity-50 px-3 py-1 text-sm"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
                <path d="M3 8.5l3.5 3.5L13 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Resolve thread
            </button>
            <button
              type="button"
              onClick={() => {
                const v = replyBody.trim();
                if (v) replyMutation.mutate(v);
              }}
              disabled={replyMutation.isPending || !replyBody.trim()}
              className="rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-50 dark:bg-zinc-700 dark:hover:bg-zinc-600 disabled:opacity-50 px-3 py-1 text-sm"
            >
              Reply
            </button>
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
}

function ReplyRow({ reply }: { reply: Reply }) {
  return (
    <li className="px-3 py-2">
      <div className="flex items-center gap-2 mb-1">
        <span
          className={[
            "text-[10px] uppercase tracking-wide rounded px-1.5 py-0.5",
            reply.author === "human"
              ? "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300"
              : "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
          ].join(" ")}
        >
          {reply.author === "human" ? "You" : "AI"}
        </span>
        <span className="text-[11px] text-zinc-500">
          {new Date(reply.created_at).toLocaleString()}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-zinc-900 dark:text-zinc-100">{reply.body}</p>
    </li>
  );
}
