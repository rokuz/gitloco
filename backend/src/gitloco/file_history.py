"""File-level git history — every commit that touched a given file path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pygit2

from gitloco.repo import WORKING_TREE_SHA

_STATUS_MAP = {
    pygit2.GIT_DELTA_ADDED: "added",
    pygit2.GIT_DELTA_DELETED: "deleted",
    pygit2.GIT_DELTA_MODIFIED: "modified",
    pygit2.GIT_DELTA_RENAMED: "renamed",
    pygit2.GIT_DELTA_COPIED: "copied",
    pygit2.GIT_DELTA_UNTRACKED: "added",
    pygit2.GIT_DELTA_TYPECHANGE: "modified",
}


@dataclass(frozen=True)
class FileHistoryCommit:
    sha: str
    short_sha: str
    author_name: str
    author_email: str
    committed_at: datetime
    subject: str
    parent_shas: list[str]
    status: str
    old_path: str | None
    new_path: str | None
    patch_text: str


@dataclass(frozen=True)
class FileAtRevision:
    file_path: str
    sha: str
    is_binary: bool
    exists: bool
    content: bytes | None


def _diff_for(repo: pygit2.Repository, commit: pygit2.Commit) -> pygit2.Diff:
    if commit.parents:
        return commit.parents[0].tree.diff_to_tree(commit.tree, context_lines=3)
    return commit.tree.diff_to_tree(swap=True, context_lines=3)


def iter_commits_touching(
    repo: pygit2.Repository,
    file_path: str,
    *,
    since_sha: str | None = None,
) -> list[FileHistoryCommit]:
    """Commits that touched ``file_path``, ordered oldest first.

    If ``since_sha`` is given, only include commits from ``since_sha`` (inclusive)
    forward to HEAD. A commit "touches" the file when ``file_path`` appears as
    either the old or new path in its first-parent diff. Renames are detected
    via libgit2's similarity heuristic.
    """
    if repo.is_empty or repo.head_is_unborn:
        return []

    head = repo.head.target
    walker = repo.walk(head, pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_TIME)

    collected: list[FileHistoryCommit] = []
    seen_since = since_sha is None  # walk newest→oldest; "include" while we haven't seen since
    # Strategy: walk all the way down; emit each commit that touches file_path.
    # If since_sha provided, stop after seeing it (it itself is included).
    for commit in walker:
        diff = _diff_for(repo, commit)
        diff.find_similar()
        for patch in diff:
            delta = patch.delta
            new_path = delta.new_file.path or None
            old_path = delta.old_file.path or None
            if new_path == file_path or old_path == file_path:
                sha = str(commit.id)
                collected.append(
                    FileHistoryCommit(
                        sha=sha,
                        short_sha=sha[:7],
                        author_name=commit.author.name,
                        author_email=commit.author.email,
                        committed_at=datetime.fromtimestamp(
                            commit.commit_time, tz=UTC
                        ),
                        subject=commit.message.splitlines()[0] if commit.message else "",
                        parent_shas=[str(p) for p in commit.parent_ids],
                        status=_STATUS_MAP.get(delta.status, "modified"),
                        old_path=old_path,
                        new_path=new_path,
                        patch_text=patch.text or "",
                    )
                )
                break
        if since_sha and str(commit.id) == since_sha:
            seen_since = True
            break

    if since_sha and not seen_since:
        # since_sha wasn't reachable from HEAD; return what we have anyway.
        pass

    collected.reverse()  # chronological: oldest first
    return collected


def working_tree_patch_for(
    repo: pygit2.Repository, file_path: str
) -> str | None:
    """Working-tree patch for ``file_path`` vs HEAD, or None if no change."""
    if repo.is_empty or repo.head_is_unborn:
        empty_tree = repo[repo.TreeBuilder().write()]
        diff = empty_tree.diff_to_workdir(
            context_lines=3,
            flags=(
                pygit2.GIT_DIFF_INCLUDE_UNTRACKED
                | pygit2.GIT_DIFF_RECURSE_UNTRACKED_DIRS
                | pygit2.GIT_DIFF_SHOW_UNTRACKED_CONTENT
            ),
        )
    else:
        head_tree = repo[repo.head.target].tree
        diff = head_tree.diff_to_workdir(
            context_lines=3,
            flags=(
                pygit2.GIT_DIFF_INCLUDE_UNTRACKED
                | pygit2.GIT_DIFF_RECURSE_UNTRACKED_DIRS
                | pygit2.GIT_DIFF_SHOW_UNTRACKED_CONTENT
            ),
        )
    for patch in diff:
        delta = patch.delta
        if delta.new_file.path == file_path or delta.old_file.path == file_path:
            return patch.text or None
    return None


def read_file_at(
    repo: pygit2.Repository, sha: str, file_path: str
) -> FileAtRevision:
    """Read ``file_path`` as it was at ``sha`` (or in the working tree)."""
    if sha == WORKING_TREE_SHA:
        if not repo.workdir:
            return FileAtRevision(file_path, sha, False, False, None)
        from pathlib import Path

        full = Path(repo.workdir) / file_path
        if not full.exists() or not full.is_file():
            return FileAtRevision(file_path, sha, False, False, None)
        try:
            data = full.read_bytes()
        except OSError:
            return FileAtRevision(file_path, sha, False, False, None)
        return FileAtRevision(file_path, sha, _is_binary(data), True, data)

    obj = repo.get(sha)
    if obj is None:
        return FileAtRevision(file_path, sha, False, False, None)
    if isinstance(obj, pygit2.Tag):
        obj = obj.peel(pygit2.Commit)
    if not isinstance(obj, pygit2.Commit):
        return FileAtRevision(file_path, sha, False, False, None)
    try:
        entry = obj.tree[file_path]
    except KeyError:
        return FileAtRevision(file_path, sha, False, False, None)
    blob = repo[entry.id]
    if not isinstance(blob, pygit2.Blob):
        return FileAtRevision(file_path, sha, False, False, None)
    data = bytes(blob.data)
    return FileAtRevision(file_path, sha, _is_binary(data), True, data)


def _is_binary(content: bytes) -> bool:
    return b"\x00" in content[:8000]
