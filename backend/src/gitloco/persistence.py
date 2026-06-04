"""Persistent-commit model.

A *persistent commit* is a logical commit that survives rebases. Its versions
are the git hashes it has been (or, for uncommitted work, content states under
the ``WORKING_TREE`` sentinel). Comment threads belong to the persistent
commit, so they are never lost when the commit is rewritten.

Lookups are plain joins — no migration or reconciliation:

  - threads on hash H      → persistent commit of H → its threads
  - versions of commit     → persistent commit of H → its CommitVersion rows
  - a rewrite H → H'       → append H' as a new version of H's persistent commit
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

import pygit2
from sqlmodel import Session, func, select

from gitloco.models import (
    CommitVersion,
    CommitVersionFile,
    PersistentCommit,
    Snapshot,
    Thread,
)
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


# ── snapshots ────────────────────────────────────────────────────────────────


def _is_binary(content: bytes) -> bool:
    return b"\x00" in content[:8000]


def _get_or_create_snapshot(
    session: Session, *, file_path: str, content: bytes
) -> Snapshot:
    content_hash = hashlib.sha256(content).hexdigest()
    existing = session.exec(
        select(Snapshot).where(Snapshot.content_hash == content_hash)
    ).first()
    if existing is not None:
        return existing
    snap = Snapshot(
        content_hash=content_hash,
        file_path=file_path,
        content=content,
        is_binary=_is_binary(content),
    )
    session.add(snap)
    session.flush()
    return snap


def snapshot_text(session: Session, snapshot_id: int | None) -> str | None:
    if snapshot_id is None:
        return None
    snap = session.get(Snapshot, snapshot_id)
    if snap is None or snap.is_binary:
        return None
    try:
        return snap.content.decode("utf-8", errors="replace")
    except Exception:
        return None


# ── git reads ────────────────────────────────────────────────────────────────


def _commit(repo: pygit2.Repository, sha: str) -> pygit2.Commit | None:
    obj = repo.get(sha)
    if isinstance(obj, pygit2.Tag):
        obj = obj.peel(pygit2.Commit)
    return obj if isinstance(obj, pygit2.Commit) else None


def commit_identity(repo: pygit2.Repository, commit_hash: str) -> dict | None:
    """Identity fields stored on a version, used to auto-link a rewritten
    commit. None for the working tree or an unknown hash."""
    if commit_hash == WORKING_TREE_SHA:
        return None
    c = _commit(repo, commit_hash)
    if c is None:
        return None
    subject = c.message.splitlines()[0] if c.message else ""
    return {
        "subject": subject,
        "author_name": c.author.name,
        "author_email": c.author.email,
        "author_time": int(c.author.time),
    }


def _read_blob(
    repo: pygit2.Repository, sha: str | None, path: str | None
) -> bytes | None:
    if sha is None or path is None:
        return None
    c = _commit(repo, sha)
    if c is None:
        return None
    try:
        entry = c.tree[path]
    except KeyError:
        return None
    blob = repo[entry.id]
    return bytes(blob.data) if isinstance(blob, pygit2.Blob) else None


def _read_workdir(repo: pygit2.Repository, path: str | None) -> bytes | None:
    if path is None or not repo.workdir:
        return None
    full = Path(repo.workdir) / path
    if not full.exists() or not full.is_file():
        return None
    try:
        return full.read_bytes()
    except OSError:
        return None


def _diff_and_parent(
    repo: pygit2.Repository, commit_hash: str
) -> tuple[pygit2.Diff, str | None]:
    wt_flags = (
        pygit2.GIT_DIFF_INCLUDE_UNTRACKED
        | pygit2.GIT_DIFF_RECURSE_UNTRACKED_DIRS
        | pygit2.GIT_DIFF_SHOW_UNTRACKED_CONTENT
    )
    if commit_hash == WORKING_TREE_SHA:
        if repo.is_empty or repo.head_is_unborn:
            empty = repo[repo.TreeBuilder().write()]
            return empty.diff_to_workdir(context_lines=3, flags=wt_flags), None
        head_sha = str(repo.head.target)
        return (
            repo[repo.head.target].tree.diff_to_workdir(
                context_lines=3, flags=wt_flags
            ),
            head_sha,
        )
    c = _commit(repo, commit_hash)
    if c is None:
        raise KeyError(commit_hash)
    if c.parents:
        parent = c.parents[0]
        return parent.tree.diff_to_tree(c.tree, context_lines=3), str(parent.id)
    return c.tree.diff_to_tree(swap=True, context_lines=3), None


# ── version capture ──────────────────────────────────────────────────────────


def _capture_files(
    session: Session, repo: pygit2.Repository, version: CommitVersion
) -> None:
    """Snapshot every file in the version's diff vs its parent."""
    commit_hash = version.commit_hash
    try:
        diff, parent_sha = _diff_and_parent(repo, commit_hash)
    except (KeyError, ValueError):
        return
    diff.find_similar()
    for patch in diff:
        delta = patch.delta
        new_path = delta.new_file.path or None
        old_path = delta.old_file.path or None
        key = new_path or old_path
        if key is None:
            continue
        parent_bytes = _read_blob(repo, parent_sha, old_path)
        if commit_hash == WORKING_TREE_SHA:
            commit_bytes = _read_workdir(repo, new_path)
        else:
            commit_bytes = _read_blob(repo, commit_hash, new_path)
        parent_snap = (
            _get_or_create_snapshot(
                session, file_path=old_path or key, content=parent_bytes
            )
            if parent_bytes is not None
            else None
        )
        commit_snap = (
            _get_or_create_snapshot(
                session, file_path=new_path or key, content=commit_bytes
            )
            if commit_bytes is not None
            else None
        )
        session.add(
            CommitVersionFile(
                version_id=version.id,
                file_path=key,
                status=_STATUS_MAP.get(delta.status, "modified"),
                old_path=old_path,
                new_path=new_path,
                parent_snapshot_id=parent_snap.id if parent_snap else None,
                commit_snapshot_id=commit_snap.id if commit_snap else None,
            )
        )


def _next_version_number(session: Session, pc_id: int) -> int:
    current = session.exec(
        select(func.max(CommitVersion.version_number)).where(
            CommitVersion.persistent_commit_id == pc_id
        )
    ).one()
    return (current or 0) + 1


def _add_version(
    session: Session, repo: pygit2.Repository, pc_id: int, commit_hash: str
) -> CommitVersion:
    identity = commit_identity(repo, commit_hash) or {}
    version = CommitVersion(
        persistent_commit_id=pc_id,
        version_number=_next_version_number(session, pc_id),
        commit_hash=commit_hash,
        **identity,
    )
    session.add(version)
    session.flush()
    _capture_files(session, repo, version)
    return version


def _fingerprint(session: Session, version: CommitVersion) -> tuple:
    rows = session.exec(
        select(CommitVersionFile).where(CommitVersionFile.version_id == version.id)
    ).all()
    out = []
    for r in rows:
        ph = session.get(Snapshot, r.parent_snapshot_id) if r.parent_snapshot_id else None
        ch = session.get(Snapshot, r.commit_snapshot_id) if r.commit_snapshot_id else None
        out.append(
            (r.file_path, ph.content_hash if ph else None, ch.content_hash if ch else None)
        )
    return tuple(sorted(out))


# ── persistent-commit resolution ─────────────────────────────────────────────


def _version_by_hash(session: Session, commit_hash: str) -> CommitVersion | None:
    return session.exec(
        select(CommitVersion)
        .where(CommitVersion.commit_hash == commit_hash)
        .order_by(CommitVersion.version_number)
    ).first()


def _identity_match_pc(
    session: Session, repo: pygit2.Repository, commit_hash: str
) -> int | None:
    """Find an existing persistent commit whose any version shares this commit's
    identity (subject + author + time) — i.e. it's the same commit rewritten."""
    identity = commit_identity(repo, commit_hash)
    if identity is None:
        return None
    match = session.exec(
        select(CommitVersion).where(
            CommitVersion.subject == identity["subject"],
            CommitVersion.author_email == identity["author_email"],
            CommitVersion.author_time == identity["author_time"],
        )
    ).first()
    return match.persistent_commit_id if match else None


def resolve_pc(
    session: Session, repo: pygit2.Repository, commit_hash: str, *, create: bool
) -> int | None:
    """Return the persistent-commit id for ``commit_hash``.

    Links the hash (as a new version) when it's an unseen rewrite of a known
    commit, or — when ``create`` — starts a fresh persistent commit. For the
    working tree, appends a version when the content changed since the last.
    """
    existing = _version_by_hash(session, commit_hash)
    if existing is not None:
        pc_id = existing.persistent_commit_id
        if commit_hash == WORKING_TREE_SHA and create:
            _maybe_capture_working_tree(session, repo, pc_id)
        return pc_id

    # An unseen real commit: maybe it's a rewrite of a known one.
    if commit_hash != WORKING_TREE_SHA:
        pc_id = _identity_match_pc(session, repo, commit_hash)
        if pc_id is not None:
            _add_version(session, repo, pc_id, commit_hash)
            return pc_id

    if not create:
        return None

    pc = PersistentCommit()
    session.add(pc)
    session.flush()
    _add_version(session, repo, pc.id, commit_hash)
    return pc.id


def _maybe_capture_working_tree(
    session: Session, repo: pygit2.Repository, pc_id: int
) -> None:
    """Capture a new working-tree version only if its content changed."""
    latest = session.exec(
        select(CommitVersion)
        .where(
            CommitVersion.persistent_commit_id == pc_id,
            CommitVersion.commit_hash == WORKING_TREE_SHA,
        )
        .order_by(CommitVersion.version_number.desc())  # type: ignore[union-attr]
    ).first()
    candidate = _add_version(session, repo, pc_id, WORKING_TREE_SHA)
    if latest is not None and _fingerprint(session, latest) == _fingerprint(
        session, candidate
    ):
        # Unchanged — drop the just-created duplicate.
        for f in session.exec(
            select(CommitVersionFile).where(
                CommitVersionFile.version_id == candidate.id
            )
        ).all():
            session.delete(f)
        session.delete(candidate)
        session.flush()


def record_rewrite(
    session: Session, repo: pygit2.Repository, old_hash: str, new_hash: str
) -> bool:
    """Append ``new_hash`` as a new version of ``old_hash``'s persistent commit.
    Returns True if a version was added."""
    pc_id = resolve_pc(session, repo, old_hash, create=False)
    if pc_id is None:
        return False
    if _version_by_hash(session, new_hash) is not None:
        return False
    _add_version(session, repo, pc_id, new_hash)
    return True


# ── queries ──────────────────────────────────────────────────────────────────


def versions_for_hash(
    session: Session, repo: pygit2.Repository, commit_hash: str
) -> list[CommitVersion]:
    pc_id = resolve_pc(session, repo, commit_hash, create=False)
    if pc_id is None:
        return []
    return list(
        session.exec(
            select(CommitVersion)
            .where(CommitVersion.persistent_commit_id == pc_id)
            .order_by(CommitVersion.version_number)
        ).all()
    )


def threads_for_hash(
    session: Session, repo: pygit2.Repository, commit_hash: str
) -> list[Thread]:
    pc_id = resolve_pc(session, repo, commit_hash, create=False)
    if pc_id is None:
        return []
    return list(
        session.exec(
            select(Thread)
            .where(Thread.persistent_commit_id == pc_id)
            .order_by(Thread.created_at)
        ).all()
    )


def reachable_shas(repo: pygit2.Repository) -> set[str]:
    if repo.is_empty or repo.head_is_unborn:
        return set()
    walker = repo.walk(repo.head.target, pygit2.GIT_SORT_TOPOLOGICAL)
    return {str(c.id) for c in walker}


def orphaned_threads(
    session: Session, repo: pygit2.Repository
) -> list[Thread]:
    """Threads whose persistent commit has no version reachable from HEAD (the
    whole logical commit was rebased away without being re-linked), so they
    appear under no current commit."""
    reachable = reachable_shas(repo)
    # pc_id -> set of its version hashes
    hashes_by_pc: dict[int, set[str]] = {}
    for v in session.exec(select(CommitVersion)).all():
        hashes_by_pc.setdefault(v.persistent_commit_id, set()).add(v.commit_hash)
    out: list[Thread] = []
    for t in session.exec(select(Thread).order_by(Thread.created_at)).all():
        hashes = hashes_by_pc.get(t.persistent_commit_id, set())
        if WORKING_TREE_SHA in hashes:
            continue  # working tree is always shown
        if not (hashes & reachable):
            out.append(t)
    return out


def latest_version(session: Session, pc_id: int) -> CommitVersion | None:
    return session.exec(
        select(CommitVersion)
        .where(CommitVersion.persistent_commit_id == pc_id)
        .order_by(CommitVersion.version_number.desc())  # type: ignore[union-attr]
    ).first()


# ── compare ──────────────────────────────────────────────────────────────────


def _version_files(session: Session, version: CommitVersion) -> dict[str, CommitVersionFile]:
    rows = session.exec(
        select(CommitVersionFile).where(CommitVersionFile.version_id == version.id)
    ).all()
    return {r.file_path: r for r in rows}


def _side_text(
    session: Session, f: CommitVersionFile | None, side: str
) -> tuple[str | None, str | None, bool]:
    """Return (text, path, is_binary) for the parent/commit side of a file."""
    if f is None:
        return None, None, False
    sid = f.parent_snapshot_id if side == "parent" else f.commit_snapshot_id
    path = f.old_path if side == "parent" else f.new_path
    if sid is None:
        return None, path, False
    snap = session.get(Snapshot, sid)
    if snap is None:
        return None, path, False
    if snap.is_binary:
        return None, path, True
    return snap.content.decode("utf-8", errors="replace"), path, False


def _unified(file_path: str, from_text: str | None, from_path: str | None,
             to_text: str | None, to_path: str | None) -> dict:
    if from_text is None and to_text is None:
        return {"file_path": file_path, "status": "unchanged", "is_binary": False,
                "old_path": from_path, "new_path": to_path, "patch_text": ""}
    a = from_text or ""
    b = to_text or ""
    if a == b and from_path == to_path:
        return {"file_path": file_path, "status": "unchanged", "is_binary": False,
                "old_path": from_path, "new_path": to_path, "patch_text": ""}
    if from_text is None:
        status, fl, tl = "added", "/dev/null", f"b/{to_path or file_path}"
    elif to_text is None:
        status, fl, tl = "deleted", f"a/{from_path or file_path}", "/dev/null"
    elif from_path != to_path:
        status, fl, tl = "renamed", f"a/{from_path}", f"b/{to_path}"
    else:
        status, fl, tl = "modified", f"a/{from_path or file_path}", f"b/{to_path or file_path}"
    body = list(difflib.unified_diff(
        a.splitlines(keepends=True), b.splitlines(keepends=True),
        fromfile=fl, tofile=tl, n=3,
    ))
    header = f"diff --git a/{from_path or file_path} b/{to_path or file_path}\n"
    patch = "".join([header, *body])
    if not patch.endswith("\n"):
        patch += "\n"
    return {"file_path": file_path, "status": status, "is_binary": False,
            "old_path": from_path, "new_path": to_path, "patch_text": patch}


def _resolve_version_ref(
    session: Session, versions: list[CommitVersion], name: str
) -> CommitVersion | None:
    """Map a picker name ('base', 'latest', 'V<n>', '<n>') to a version (None =
    base, the parent side of the latest)."""
    n = name.strip().lower()
    if n == "base":
        return None
    if n == "latest":
        return versions[-1] if versions else None
    num = int(n[1:]) if n.startswith("v") else int(n)
    for v in versions:
        if v.version_number == num:
            return v
    raise ValueError(f"no version {name}")


def compare(
    session: Session, repo: pygit2.Repository, commit_hash: str,
    from_name: str, to_name: str,
) -> dict:
    versions = versions_for_hash(session, repo, commit_hash)
    if not versions:
        return {"from_name": from_name, "to_name": to_name,
                "from_version": None, "to_version": None, "files": []}
    from_v = _resolve_version_ref(session, versions, from_name)
    to_v = _resolve_version_ref(session, versions, to_name) or versions[-1]
    to_files = _version_files(session, to_v)

    files = []
    if from_v is None:  # base → to: parent side vs commit side of the to-version
        for path, f in to_files.items():
            ft, fp, fb = _side_text(session, f, "parent")
            tt, tp, tb = _side_text(session, f, "commit")
            if fb or tb:
                files.append({"file_path": path, "status": "binary", "is_binary": True,
                              "old_path": fp, "new_path": tp, "patch_text": ""})
            else:
                files.append(_unified(path, ft, fp, tt, tp))
    else:
        from_files = _version_files(session, from_v)
        for path in sorted(set(from_files) | set(to_files)):
            ft, fp, fb = _side_text(session, from_files.get(path), "commit")
            tt, tp, tb = _side_text(session, to_files.get(path), "commit")
            if fb or tb:
                files.append({"file_path": path, "status": "binary", "is_binary": True,
                              "old_path": fp, "new_path": tp, "patch_text": ""})
            else:
                files.append(_unified(path, ft, fp, tt, tp))
    return {"from_name": from_name, "to_name": to_name,
            "from_version": from_v.version_number if from_v else None,
            "to_version": to_v.version_number, "files": files}
