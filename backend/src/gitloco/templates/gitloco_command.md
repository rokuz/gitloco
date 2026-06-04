---
description: Address open GitLoco threads (oldest commit first), fixing each in its original commit via rebase, then leave the human to resolve.
---

# /gitloco

GitLoco is the local code-review tool running alongside this repo. The human has left review comments on specific lines of specific commits. Your job is to work through every open thread in **chronological commit order** (oldest first) and address each one before moving to the next.

## Loop

Repeat until `list_open_threads` returns an empty array:

1. **Fetch the next batch of open threads** with the MCP tool `list_open_threads`. The order returned is the order you must work in (oldest commit first; `WORKING_TREE` last).

2. **For each thread, in returned order:**

   a. Call `get_thread` with the thread id. Read:
      - The `replies` array (the human's first comment + any back-and-forth).
      - `parent_content` and `commit_content` — the **primary** (commented) file as it was on each side of the commit's diff at thread-creation time. These survive any rebase you may do.
      - `all_files` — snapshots of **every** file touched by the commit (parent + commit sides per file). Use this when your fix may span multiple files — the human's intent might require coordinated changes across the whole commit.
      - `history_since` — every commit (oldest first) that touched the primary file from the commented commit forward to HEAD, each with `patch_text`.
      - `working_tree_patch` — current working-tree diff for the primary file (null if clean).
      - `current_content` — the primary file as it lives on disk right now.
      - `commit_sha`, `file_path`, `line_side` (`old` | `new`), `line_number`.

   b. **Check whether the comment still applies.** The repo may have changed since the comment was written (especially after you've rebased earlier commits). Compare the snapshot contents to the current state of `file_path`. If the issue no longer exists, call `reply_to_thread` explaining that and move on.

   c. **Decide: clarification or change?**
      - **Clarification.** If you don't have enough information to act, post a focused, single-question reply via `reply_to_thread`. Stop the loop for this thread — the human will reply later and `/gitloco` will be re-run.
      - **Change.** If the comment is actionable, apply the fix **inside the original commit** (`commit_sha`) via interactive rebase:
        - `git rebase -i <commit_sha>^` (or `--root` for the initial commit), set the target commit to `edit`.
        - Edit the file(s) to address the comment.
        - `git add` the changes, then `git commit --amend --no-edit`. Note the commit's **new** SHA (e.g. `git rev-parse HEAD`) — you'll need it next.
        - `git rebase --continue` and resolve any conflicts that arise from later commits applying on top.
        - **Record the rewrite so the thread stays attached:** call `record_commit_rewrite(old_sha, new_sha)` with the thread's original `commit_sha` and the SHA the commit became after your amend. Without this the thread can be orphaned on the old SHA and the human won't be able to resolve it. (GitLoco also auto-detects rewrites by commit identity, but recording it is exact — always do it.)
        - Then call `reply_to_thread` with a short note: what you changed and which (new) SHA the fix lives in.

3. **Do not call any "resolve" tool.** There isn't one. Humans review your replies and resolve threads themselves via the GitLoco UI.

4. **When `list_open_threads` returns `[]`:** Report to the user: "All open threads addressed — review them in GitLoco." Then stop.

## Special cases

- **WORKING_TREE threads.** The `commit_sha` is the literal string `WORKING_TREE`. Don't rebase — these are uncommitted changes. Edit the file in the working tree directly (or unstage / re-stage as needed) and reply describing what changed.
- **Stacked edits in one commit.** If multiple threads target the same commit, address them all in a single `git rebase` session before continuing — one rebase per commit, not per thread.
- **Conflicts during rebase.** Resolve them and keep going. If a conflict is genuinely ambiguous, do not guess — post a `reply_to_thread` asking the human, abort the rebase (`git rebase --abort`), and move to the next thread.

## Tools you have

- `list_open_threads(commit_sha?)` — get threads to work on, in order.
- `get_thread(thread_id)` — full context including snapshots, history_since, working_tree_patch, current_content.
- `reply_to_thread(thread_id, body)` — your way to talk back to the human.
- `record_commit_rewrite(old_sha, new_sha)` — call right after you amend/rebase a commit so threads follow it to the new SHA.
- `get_commit_diff(commit_sha)` — view a commit's diff if you need context.
- `get_file_history(file_path, since_commit_sha?)` — every commit that touched a file, with patches.
- `get_file_at(commit_sha, file_path)` — file content at any revision (use `"WORKING_TREE"` for the on-disk state).
- `list_commits_tool()` — list of commits if you need to navigate.

Start now.
