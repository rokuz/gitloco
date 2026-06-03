from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pygit2
from mcp.server.fastmcp import FastMCP
from sqlalchemy import Engine
from sqlmodel import Session, select

from gitloco.diff import get_diff
from gitloco.file_history import (
    iter_commits_touching,
    read_file_at,
    working_tree_patch_for,
)
from gitloco.models import CommitVersion, CommitVersionFile, Reply, Thread
from gitloco.repo import WORKING_TREE_SHA, list_commits
from gitloco.snapshots import snapshot_text as _snapshot_text_helper


def _thread_dict(thread: Thread, *, engine: Engine) -> dict[str, Any]:
    with Session(engine) as session:
        thread_full = session.get(Thread, thread.id)
        if thread_full is None:
            return {}
        replies = [
            {
                "id": r.id,
                "author": r.author,
                "body": r.body,
                "created_at": r.created_at.isoformat(),
            }
            for r in thread_full.replies
        ]
        return {
            "id": thread_full.id,
            "commit_sha": thread_full.commit_sha,
            "file_path": thread_full.file_path,
            "line_side": thread_full.line_side,
            "line_number": thread_full.line_number,
            "status": thread_full.status,
            "created_at": thread_full.created_at.isoformat(),
            "resolved_at": thread_full.resolved_at.isoformat()
            if thread_full.resolved_at
            else None,
            "replies": replies,
        }


def _commit_time(repo: pygit2.Repository, sha: str) -> datetime:
    if sha == WORKING_TREE_SHA:
        return datetime.max.replace(tzinfo=timezone.utc)
    obj = repo.get(sha)
    if obj is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(obj, pygit2.Tag):
        obj = obj.peel(pygit2.Commit)
    if not isinstance(obj, pygit2.Commit):
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(obj.commit_time, tz=timezone.utc)


def _snapshot_text(session: Session, snapshot_id: int | None) -> str | None:
    return _snapshot_text_helper(session, snapshot_id)


def build_mcp(*, engine: Engine, repo: pygit2.Repository, repo_path: str) -> FastMCP:
    """Build the MCP server exposing GitLoco's review surface to AI agents."""
    mcp = FastMCP(
        name="gitloco",
        instructions=(
            f"GitLoco — local code review for repo {repo_path}. "
            "Use list_open_threads to find work, get_thread for full context, "
            "and reply_to_thread to respond. Address threads in the order they are returned "
            "(oldest commit first). Humans resolve threads; you do not."
        ),
        # We mount the resulting Starlette app under /mcp in our FastAPI app,
        # so the inner endpoint must be at "/" or the URL doubles up.
        streamable_http_path="/",
    )

    @mcp.tool()
    def list_open_threads(commit_sha: str | None = None) -> list[dict[str, Any]]:
        """List open threads to address, oldest commit first.

        Args:
            commit_sha: Optional. Restrict to threads anchored to this commit.

        Returns: Array of thread summaries ordered by the commit's chronology.
        Always work through these in returned order.
        """
        with Session(engine) as session:
            stmt = select(Thread).where(Thread.status == "open")
            if commit_sha:
                stmt = stmt.where(Thread.commit_sha == commit_sha)
            threads = list(session.exec(stmt).all())
            threads.sort(key=lambda t: (_commit_time(repo, t.commit_sha), t.created_at))
            return [
                {
                    "id": t.id,
                    "commit_sha": t.commit_sha,
                    "file_path": t.file_path,
                    "line_side": t.line_side,
                    "line_number": t.line_number,
                    "status": t.status,
                    "first_message": (t.replies[0].body if t.replies else None),
                    "reply_count": len(t.replies),
                }
                for t in threads
            ]

    @mcp.tool()
    def get_thread(thread_id: int) -> dict[str, Any]:
        """Get a thread with full context for addressing it.

        Includes:
        - All replies (alternating human/agent).
        - parent_content / commit_content: text of the **primary** (commented)
          file on each side of the diff, captured when the thread was created.
        - all_files: snapshots for **every** file touched by the commit (not
          just the commented one) — each item has parent_content, commit_content,
          status, and is_primary. Use this when a fix may span multiple files.
        - history_since: every commit (oldest first) that touched the primary
          file from the thread's commit forward to HEAD — each item carries a
          unified patch (`patch_text`). Use this to judge whether the comment
          still applies after subsequent edits or rebases.
        - working_tree_patch: the primary file's diff between HEAD and the
          working tree, or null if clean.
        - current_content: the primary file's text in the working tree right
          now (or null if missing/binary).
        """
        with Session(engine) as session:
            thread = session.get(Thread, thread_id)
            if thread is None:
                raise ValueError(f"thread {thread_id} not found")
            parent_text = _snapshot_text(session, thread.parent_snapshot_id)
            commit_text = _snapshot_text(session, thread.commit_snapshot_id)
            replies = [
                {
                    "id": r.id,
                    "author": r.author,
                    "body": r.body,
                    "created_at": r.created_at.isoformat(),
                }
                for r in thread.replies
            ]
            # Use the *latest* commit version on this sha for all_files (most
            # recent human-action snapshot). Versions before this one are
            # available via list_commit_versions / get_commit_version.
            latest_version = session.exec(
                select(CommitVersion)
                .where(CommitVersion.commit_sha == thread.commit_sha)
                .order_by(CommitVersion.version_number.desc())  # type: ignore[union-attr]
            ).first()
            all_files = []
            latest_version_number: int | None = None
            if latest_version is not None:
                latest_version_number = latest_version.version_number
                file_rows = list(
                    session.exec(
                        select(CommitVersionFile)
                        .where(CommitVersionFile.version_id == latest_version.id)
                        .order_by(CommitVersionFile.file_path)
                    ).all()
                )
                all_files = [
                    {
                        "file_path": c.file_path,
                        "status": c.status,
                        "old_path": c.old_path,
                        "new_path": c.new_path,
                        "parent_content": _snapshot_text(session, c.parent_snapshot_id),
                        "commit_content": _snapshot_text(session, c.commit_snapshot_id),
                        "is_primary": c.file_path == thread.file_path,
                    }
                    for c in file_rows
                ]
            base_payload: dict[str, Any] = {
                "id": thread.id,
                "commit_sha": thread.commit_sha,
                "file_path": thread.file_path,
                "line_side": thread.line_side,
                "line_number": thread.line_number,
                "status": thread.status,
                "created_at": thread.created_at.isoformat(),
                "resolved_at": thread.resolved_at.isoformat()
                if thread.resolved_at
                else None,
                "replies": replies,
                "parent_content": parent_text,
                "commit_content": commit_text,
                "all_files": all_files,
                "latest_version_number": latest_version_number,
            }

        # history_since: only meaningful for real commits, not WORKING_TREE.
        since_sha = (
            thread.commit_sha if thread.commit_sha != WORKING_TREE_SHA else None
        )
        history = iter_commits_touching(repo, thread.file_path, since_sha=since_sha)
        base_payload["history_since"] = [
            {
                "sha": c.sha,
                "short_sha": c.short_sha,
                "author_name": c.author_name,
                "committed_at": c.committed_at.isoformat(),
                "subject": c.subject,
                "status": c.status,
                "old_path": c.old_path,
                "new_path": c.new_path,
                "patch_text": c.patch_text,
            }
            for c in history
        ]
        base_payload["working_tree_patch"] = working_tree_patch_for(
            repo, thread.file_path
        )
        current = read_file_at(repo, WORKING_TREE_SHA, thread.file_path)
        if current.exists and not current.is_binary and current.content is not None:
            base_payload["current_content"] = current.content.decode(
                "utf-8", errors="replace"
            )
        else:
            base_payload["current_content"] = None
        return base_payload

    @mcp.tool()
    def reply_to_thread(thread_id: int, body: str) -> dict[str, Any]:
        """Post a reply on an open thread as the AI agent.

        Use this to (a) ask the human a clarifying question, or (b) describe
        the fix you applied to the original commit via rebase.
        """
        if not body.strip():
            raise ValueError("body must not be empty")
        with Session(engine) as session:
            thread = session.get(Thread, thread_id)
            if thread is None:
                raise ValueError(f"thread {thread_id} not found")
            if thread.status == "resolved":
                raise ValueError("thread is resolved")
            reply = Reply(thread_id=thread_id, author="agent", body=body)
            session.add(reply)
            session.commit()
            session.refresh(thread)
            return {"thread_id": thread.id, "reply_id": reply.id}

    @mcp.tool()
    def list_commits_tool() -> list[dict[str, Any]]:
        """List commits in the repository (topological order, newest first)."""
        return [
            {
                "sha": c.sha,
                "short_sha": c.short_sha,
                "author_name": c.author_name,
                "committed_at": c.committed_at.isoformat(),
                "subject": c.subject,
                "parent_shas": c.parent_shas,
            }
            for c in list_commits(repo)
        ]

    @mcp.tool()
    def list_commit_versions(commit_sha: str) -> list[dict[str, Any]]:
        """List every captured version (V1, V2, ...) of a commit, oldest first.

        Each version was captured at a human action moment (thread creation or
        human reply) and contains the full file set of the commit's diff vs
        its parent at that point in time.
        """
        with Session(engine) as session:
            rows = list(
                session.exec(
                    select(CommitVersion)
                    .where(CommitVersion.commit_sha == commit_sha)
                    .order_by(CommitVersion.version_number)
                ).all()
            )
            return [
                {
                    "version_number": v.version_number,
                    "created_at": v.created_at.isoformat(),
                    "trigger": v.trigger,
                    "triggering_thread_id": v.triggering_thread_id,
                    "triggering_reply_id": v.triggering_reply_id,
                }
                for v in rows
            ]

    @mcp.tool()
    def get_commit_version(
        commit_sha: str, version_number: int
    ) -> dict[str, Any]:
        """Get a specific captured version of a commit, with all files (both
        sides) as text."""
        with Session(engine) as session:
            version = session.exec(
                select(CommitVersion).where(
                    CommitVersion.commit_sha == commit_sha,
                    CommitVersion.version_number == version_number,
                )
            ).first()
            if version is None:
                raise ValueError(
                    f"commit {commit_sha} has no version {version_number}"
                )
            files = list(
                session.exec(
                    select(CommitVersionFile)
                    .where(CommitVersionFile.version_id == version.id)
                    .order_by(CommitVersionFile.file_path)
                ).all()
            )
            return {
                "version_number": version.version_number,
                "created_at": version.created_at.isoformat(),
                "trigger": version.trigger,
                "triggering_thread_id": version.triggering_thread_id,
                "triggering_reply_id": version.triggering_reply_id,
                "files": [
                    {
                        "file_path": f.file_path,
                        "status": f.status,
                        "old_path": f.old_path,
                        "new_path": f.new_path,
                        "parent_content": _snapshot_text(session, f.parent_snapshot_id),
                        "commit_content": _snapshot_text(session, f.commit_snapshot_id),
                    }
                    for f in files
                ],
            }

    @mcp.tool()
    def get_file_history(
        file_path: str, since_commit_sha: str | None = None
    ) -> dict[str, Any]:
        """Get the chronological evolution of a file: every commit that touched
        it (oldest first) with its unified patch, plus the working-tree diff
        if dirty.

        Args:
            file_path: Repo-relative path (e.g. "src/foo/bar.py").
            since_commit_sha: Optional. If provided, only include commits from
                this SHA forward to HEAD; otherwise include the full history.
        """
        commits = iter_commits_touching(repo, file_path, since_sha=since_commit_sha)
        wt = working_tree_patch_for(repo, file_path)
        return {
            "file_path": file_path,
            "since": since_commit_sha,
            "commits": [
                {
                    "sha": c.sha,
                    "short_sha": c.short_sha,
                    "author_name": c.author_name,
                    "committed_at": c.committed_at.isoformat(),
                    "subject": c.subject,
                    "status": c.status,
                    "old_path": c.old_path,
                    "new_path": c.new_path,
                    "patch_text": c.patch_text,
                }
                for c in commits
            ],
            "working_tree_patch": wt,
        }

    @mcp.tool()
    def get_file_at(commit_sha: str, file_path: str) -> dict[str, Any]:
        """Get the content of a file as it was at a specific commit.

        Args:
            commit_sha: A real commit SHA, or the literal "WORKING_TREE" to
                read the current on-disk file.
            file_path: Repo-relative path.

        Returns: {file_path, sha, exists, is_binary, content}. ``content`` is
        the file as text (utf-8 with replacement for invalid bytes), or null
        when the file is missing or binary.
        """
        snap = read_file_at(repo, commit_sha, file_path)
        if not snap.exists:
            return {
                "file_path": file_path,
                "sha": commit_sha,
                "exists": False,
                "is_binary": False,
                "content": None,
            }
        content_text: str | None = None
        if not snap.is_binary and snap.content is not None:
            content_text = snap.content.decode("utf-8", errors="replace")
        return {
            "file_path": file_path,
            "sha": commit_sha,
            "exists": True,
            "is_binary": snap.is_binary,
            "content": content_text,
        }

    @mcp.tool()
    def get_commit_diff(commit_sha: str) -> list[dict[str, Any]]:
        """Get the file-by-file unified diff of a commit vs its first parent
        (or the working tree if commit_sha == 'WORKING_TREE')."""
        try:
            files = get_diff(repo, commit_sha)
        except KeyError as exc:
            raise ValueError(f"commit {commit_sha} not found") from exc
        return [
            {
                "old_path": f.old_path,
                "new_path": f.new_path,
                "status": f.status,
                "is_binary": f.is_binary,
                "patch_text": f.patch_text,
            }
            for f in files
        ]

    return mcp
