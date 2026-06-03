import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { LineSide } from "../api/types";

interface Props {
  commitSha: string;
  filePath: string;
  lineSide: LineSide;
  lineNumber: number;
  onCancel: () => void;
  onCreated: () => void;
}

export function NewThreadComposer({
  commitSha,
  filePath,
  lineSide,
  lineNumber,
  onCancel,
  onCreated,
}: Props) {
  const [body, setBody] = useState("");
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    ref.current?.focus();
  }, []);

  const mutation = useMutation({
    mutationFn: () =>
      api.createThread({
        commit_sha: commitSha,
        file_path: filePath,
        line_side: lineSide,
        line_number: lineNumber,
        body,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      onCreated();
    },
  });

  return (
    <div className="my-2 rounded border border-zinc-700 bg-zinc-900 p-2 space-y-2">
      <div className="text-[11px] text-zinc-500">
        New thread on {filePath}:{lineNumber} ({lineSide})
      </div>
      <textarea
        ref={ref}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="What do you think about this line?"
        rows={3}
        className="w-full resize-y rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-zinc-100 focus:outline-none focus:border-zinc-500"
      />
      {mutation.error && (
        <div className="text-xs text-red-400">{String(mutation.error)}</div>
      )}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1 text-sm text-zinc-300 hover:text-zinc-100"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => {
            if (body.trim()) mutation.mutate();
          }}
          disabled={mutation.isPending || !body.trim()}
          className="rounded bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 px-3 py-1 text-sm text-zinc-50"
        >
          Comment
        </button>
      </div>
    </div>
  );
}
