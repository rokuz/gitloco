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
) -> tuple[CommitVersion | None, Snapshot | None, Snapshot | None]:
    """Capture the commit's current content as a version — but ONLY if it
    differs from the latest captured version.

    Versions track distinct content *states* of the commit, not comment
    actions: leaving a comment when nothing changed reuses the existing
    version (no duplicate). A new version appears when the content actually
    changes — e.g. the AI amends/rebases the commit, or the working tree is
    edited.

    Returns ``(version_or_None, parent_snapshot, commit_snapshot)`` where the
    snapshots are for ``primary_file_path`` so callers can denormalize onto a
    Thread. ``version`` is None when no new version was needed (content
    unchanged) or the diff couldn't be computed.
    """
    try:
        diff, parent_sha = _diff_and_parent_sha(repo, commit_sha)
    except (KeyError, ValueError):
        return None, None, None
    diff.find_similar()

    # Walk the diff once and materialize the snapshots (globally deduped by
    # content hash) without committing to a version yet.
    file_records: list[dict] = []
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

        file_records.append(
            {
                "file_path": file_path_key,
                "status": status,
                "old_path": old_path,
                "new_path": new_path,
                "parent_snap": parent_snap,
                "commit_snap": commit_snap,
            }
        )

        if primary_file_path and file_path_key == primary_file_path:
            primary_parent = parent_snap
            primary_commit = commit_snap
            seen_primary = True

    # Edge case: the commented file isn't actually touched by this commit
    # (e.g. clicked on a "normal" context line). Capture it so we preserve what
    # the human was looking at — but don't add it to the version file set.
    if primary_file_path and not seen_primary:
        if commit_sha == WORKING_TREE_SHA:
            pc = _read_workdir_file(repo, primary_file_path)
        else:
            pc = _read_blob_at_commit(repo, commit_sha, primary_file_path)
        pp = _read_blob_at_commit(repo, parent_sha, primary_file_path)
        if pc is not None:
            primary_commit = _get_or_create_snapshot(
                session,
                file_path=primary_file_path,
                content=pc,
                originating_commit_sha=(
                    None if commit_sha == WORKING_TREE_SHA else commit_sha
                ),
                kind=("working_tree" if commit_sha == WORKING_TREE_SHA else "commit"),
            )
        if pp is not None:
            primary_parent = _get_or_create_snapshot(
                session,
                file_path=primary_file_path,
                content=pp,
                originating_commit_sha=parent_sha,
                kind="parent",
            )

    # Content fingerprint of this state — dedup against the latest version.
    fingerprint = _fingerprint(file_records)
    latest = session.exec(
        select(CommitVersion)
        .where(CommitVersion.commit_sha == commit_sha)
        .order_by(CommitVersion.version_number.desc())  # type: ignore[union-attr]
    ).first()
    if latest is not None and _version_fingerprint(session, latest) == fingerprint:
        # Content unchanged since the last version — no new version needed.
        return None, primary_parent, primary_commit

    version = CommitVersion(
        commit_sha=commit_sha,
        version_number=_next_version_number(session, commit_sha),
        trigger=trigger,
        triggering_thread_id=triggering_thread_id,
        triggering_reply_id=triggering_reply_id,
    )
    session.add(version)
    session.flush()  # assign version.id
    for rec in file_records:
        session.add(
            CommitVersionFile(
                version_id=version.id,  # type: ignore[arg-type]
                file_path=rec["file_path"],
                status=rec["status"],
                old_path=rec["old_path"],
                new_path=rec["new_path"],
                parent_snapshot_id=rec["parent_snap"].id if rec["parent_snap"] else None,
                commit_snapshot_id=rec["commit_snap"].id if rec["commit_snap"] else None,
            )
        )
    return version, primary_parent, primary_commit


def _fingerprint(file_records: list[dict]) -> tuple:
    """A stable content fingerprint for a set of captured files: which files,
    and their parent/commit content hashes."""
    return tuple(
        sorted(
            (
                rec["file_path"],
                rec["parent_snap"].content_hash if rec["parent_snap"] else None,
                rec["commit_snap"].content_hash if rec["commit_snap"] else None,
            )
            for rec in file_records
        )
    )


def _version_fingerprint(session: Session, version: CommitVersion) -> tuple:
    """Same fingerprint shape, computed from a stored version's files."""
    rows = session.exec(
        select(CommitVersionFile).where(CommitVersionFile.version_id == version.id)
    ).all()
    out = []
    for r in rows:
        parent_hash = None
        commit_hash = None
        if r.parent_snapshot_id is not None:
            s = session.get(Snapshot, r.parent_snapshot_id)
            parent_hash = s.content_hash if s else None
        if r.commit_snapshot_id is not None:
            s = session.get(Snapshot, r.commit_snapshot_id)
            commit_hash = s.content_hash if s else None
        out.append((r.file_path, parent_hash, commit_hash))
    return tuple(sorted(out))


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
