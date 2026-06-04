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

  return (
    <div className="my-2 rounded border border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 text-sm">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-zinc-200 dark:border-zinc-800 text-xs">
        <span className="text-zinc-600 dark:text-zinc-400">
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
      </div>
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
              className="text-xs text-emerald-700 hover:text-emerald-800 dark:text-emerald-300 dark:hover:text-emerald-200 disabled:opacity-50"
            >
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
