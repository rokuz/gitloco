"""Snapshot capture — store the file contents the human was looking at so
comment anchors and the surrounding multi-file commit context survive
subsequent rebases / SHA rewrites.

Every human action on a commit (thread creation or human reply) produces a new
``CommitVersion`` row, numbered sequentially per commit (V1, V2, V3...). Each
version captures the full file set of the commit's diff vs its parent — not
just the commented file — because a fix may span multiple files.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pygit2
from sqlmodel import Session, func, select

from gitloco.models import CommitVersion, CommitVersionFile, Snapshot
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


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_probably_binary(content: bytes) -> bool:
    return b"\x00" in content[:8000]


def _get_or_create_snapshot(
    session: Session,
    *,
    file_path: str,
    content: bytes,
    originating_commit_sha: str | None,
    kind: str,
) -> Snapshot:
    content_hash = _hash(content)
    existing = session.exec(
        select(Snapshot).where(Snapshot.content_hash == content_hash)
    ).first()
    if existing is not None:
        return existing
    snapshot = Snapshot(
        content_hash=content_hash,
        file_path=file_path,
        content=content,
        is_binary=_is_probably_binary(content),
        originating_commit_sha=originating_commit_sha,
        originating_kind=kind,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _read_blob_at_commit(
    repo: pygit2.Repository, commit_sha: str | None, file_path: str | None
) -> bytes | None:
    if commit_sha is None or file_path is None:
        return None
    obj = repo.get(commit_sha)
    if obj is None:
        return None
    if isinstance(obj, pygit2.Tag):
        obj = obj.peel(pygit2.Commit)
    if not isinstance(obj, pygit2.Commit):
        return None
    try:
        entry = obj.tree[file_path]
    except KeyError:
        return None
    blob = repo[entry.id]
    if not isinstance(blob, pygit2.Blob):
        return None
    return bytes(blob.data)


def _read_workdir_file(repo: pygit2.Repository, file_path: str | None) -> bytes | None:
    if file_path is None or not repo.workdir:
        return None
    full = Path(repo.workdir) / file_path
    if not full.exists() or not full.is_file():
        return None
    try:
        return full.read_bytes()
    except OSError:
        return None


def _diff_and_parent_sha(
    repo: pygit2.Repository, commit_sha: str
) -> tuple[pygit2.Diff, str | None]:
    if commit_sha == WORKING_TREE_SHA:
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
            return diff, None
        head_sha = str(repo.head.target)
        head_tree = repo[repo.head.target].tree
        diff = head_tree.diff_to_workdir(
            context_lines=3,
            flags=(
                pygit2.GIT_DIFF_INCLUDE_UNTRACKED
                | pygit2.GIT_DIFF_RECURSE_UNTRACKED_DIRS
                | pygit2.GIT_DIFF_SHOW_UNTRACKED_CONTENT
            ),
        )
        return diff, head_sha

    obj = repo.get(commit_sha)
    if obj is None:
        raise KeyError(commit_sha)
    if isinstance(obj, pygit2.Tag):
        obj = obj.peel(pygit2.Commit)
    if not isinstance(obj, pygit2.Commit):
        raise ValueError(f"{commit_sha} is not a commit")
    if obj.parents:
        parent = obj.parents[0]
        return parent.tree.diff_to_tree(obj.tree, context_lines=3), str(parent.id)
    return obj.tree.diff_to_tree(swap=True, context_lines=3), None


def _next_version_number(session: Session, commit_sha: str) -> int:
    current_max = session.exec(
        select(func.max(CommitVersion.version_number)).where(
            CommitVersion.commit_sha == commit_sha
        )
    ).one()
    return (current_max or 0) + 1


def capture_version(
    *,
    repo: pygit2.Repository,
    session: Session,
    commit_sha: str,
    trigger: str,
    triggering_thread_id: int | None,
    triggering_reply_id: int | None,
    primary_file_path: str | None = None,
) -> tuple[CommitVersion, Snapshot | None, Snapshot | None]:
    """Capture a new V_n for ``commit_sha``: walk the commit's diff and store a
    ``CommitVersionFile`` row per file, with deduped ``Snapshot`` rows on both
    sides. Returns the version + (parent_snapshot, commit_snapshot) for the
    ``primary_file_path`` (so callers can also denormalize onto Thread).
    """
    version = CommitVersion(
        commit_sha=commit_sha,
        version_number=_next_version_number(session, commit_sha),
        trigger=trigger,
        triggering_thread_id=triggering_thread_id,
        triggering_reply_id=triggering_reply_id,
    )
    session.add(version)
    session.flush()  # assign version.id

    try:
        diff, parent_sha = _diff_and_parent_sha(repo, commit_sha)
    except (KeyError, ValueError):
        return version, None, None
    diff.find_similar()

    primary_parent: Snapshot | None = None
    primary_commit: Snapshot | None = None
    seen_primary = False

    for patch in diff:
        delta = patch.delta
        new_path = delta.new_file.path or None
        old_path = delta.old_file.path or None
        status = _STATUS_MAP.get(delta.status, "modified")
        file_path_key = new_path or old_path
        if file_path_key is None:
            continue

        parent_bytes = _read_blob_at_commit(repo, parent_sha, old_path)
        if commit_sha == WORKING_TREE_SHA:
            commit_bytes = _read_workdir_file(repo, new_path)
        else:
            commit_bytes = _read_blob_at_commit(repo, commit_sha, new_path)

        parent_snap = (
            _get_or_create_snapshot(
                session,
                file_path=old_path or file_path_key,
                content=parent_bytes,
                originating_commit_sha=parent_sha,
                kind="parent",
            )
            if parent_bytes is not None
            else None
        )
        commit_snap = (
            _get_or_create_snapshot(
                session,
                file_path=new_path or file_path_key,
                content=commit_bytes,
                originating_commit_sha=(
                    None if commit_sha == WORKING_TREE_SHA else commit_sha
                ),
                kind=("working_tree" if commit_sha == WORKING_TREE_SHA else "commit"),
            )
            if commit_bytes is not None
            else None
        )

        session.add(
            CommitVersionFile(
                version_id=version.id,  # type: ignore[arg-type]
                file_path=file_path_key,
                status=status,
                old_path=old_path,
                new_path=new_path,
                parent_snapshot_id=parent_snap.id if parent_snap else None,
                commit_snapshot_id=commit_snap.id if commit_snap else None,
            )
        )

        if primary_file_path and file_path_key == primary_file_path:
            primary_parent = parent_snap
            primary_commit = commit_snap
            seen_primary = True

    # Edge case: the commented file isn't actually touched by this commit
    # (e.g. clicked on a "normal" context line). Capture it explicitly so we
    # preserve what the human was looking at.
    if primary_file_path and not seen_primary:
        if commit_sha == WORKING_TREE_SHA:
            commit_bytes = _read_workdir_file(repo, primary_file_path)
        else:
            commit_bytes = _read_blob_at_commit(repo, commit_sha, primary_file_path)
        parent_bytes = _read_blob_at_commit(repo, parent_sha, primary_file_path)
        if commit_bytes is not None:
            primary_commit = _get_or_create_snapshot(
                session,
                file_path=primary_file_path,
                content=commit_bytes,
                originating_commit_sha=(
                    None if commit_sha == WORKING_TREE_SHA else commit_sha
                ),
                kind=("working_tree" if commit_sha == WORKING_TREE_SHA else "commit"),
            )
        if parent_bytes is not None:
            primary_parent = _get_or_create_snapshot(
                session,
                file_path=primary_file_path,
                content=parent_bytes,
                originating_commit_sha=parent_sha,
                kind="parent",
            )

    return version, primary_parent, primary_commit


def snapshot_text(session: Session, snapshot_id: int | None) -> str | None:
    """Decode a snapshot to utf-8 text. Returns None for missing/binary."""
    if snapshot_id is None:
        return None
    snap = session.get(Snapshot, snapshot_id)
    if snap is None or snap.is_binary:
        return None
    try:
        return snap.content.decode("utf-8", errors="replace")
    except Exception:
        return None
