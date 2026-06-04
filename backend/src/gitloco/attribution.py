"""Keep comment threads attached to their commit across a rebase.

A thread is anchored to a commit SHA. When the AI rebases/amends that commit
its SHA changes, orphaning the thread. We re-attach it two ways, in order:

  1. Explicit rewrite chain — `CommitRewrite(old_sha → new_sha)` rows recorded
     by the agent (or the REST/MCP layer) are followed transitively to the
     commit that is currently reachable from HEAD.
  2. Identity match — the thread stores the anchored commit's identity
     (subject + author name/email + author time) at creation. Those survive a
     rebase/amend even though the SHA changes, so an orphaned thread is matched
     to the reachable commit with the same identity (only when the match is
     unambiguous).

Reconciliation migrates `Thread.commit_sha` forward in place, so all the
existing "filter threads by sha" lookups keep working unchanged.
"""

from __future__ import annotations

import pygit2
from sqlmodel import Session, select

from gitloco.models import CommitRewrite, CommitVersion, Thread
from gitloco.repo import WORKING_TREE_SHA

IdentityKey = tuple[str, str, int]  # (subject, author_email, author_time)


def _identity_of(commit: pygit2.Commit) -> IdentityKey:
    subject = commit.message.splitlines()[0] if commit.message else ""
    return (subject, commit.author.email or "", int(commit.author.time))


def reachable_shas(repo: pygit2.Repository) -> set[str]:
    """SHAs reachable from HEAD — i.e. commits that are actually in the current
    history (a rebased-away commit object may still exist but is unreachable)."""
    if repo.is_empty or repo.head_is_unborn:
        return set()
    walker = repo.walk(repo.head.target, pygit2.GIT_SORT_TOPOLOGICAL)
    return {str(c.id) for c in walker}


def _identity_index(
    repo: pygit2.Repository, shas: set[str]
) -> dict[IdentityKey, list[str]]:
    index: dict[IdentityKey, list[str]] = {}
    for sha in shas:
        obj = repo.get(sha)
        if isinstance(obj, pygit2.Commit):
            index.setdefault(_identity_of(obj), []).append(sha)
    return index


def get_commit_identity(repo: pygit2.Repository, sha: str) -> dict | None:
    """Identity fields to store on a Thread at creation. None for the
    working-tree pseudo-commit or an unknown SHA."""
    if sha == WORKING_TREE_SHA:
        return None
    obj = repo.get(sha)
    if isinstance(obj, pygit2.Tag):
        obj = obj.peel(pygit2.Commit)
    if not isinstance(obj, pygit2.Commit):
        return None
    subject = obj.message.splitlines()[0] if obj.message else ""
    return {
        "commit_subject": subject,
        "commit_author_name": obj.author.name,
        "commit_author_email": obj.author.email,
        "commit_author_time": int(obj.author.time),
    }


def _follow_rewrites(
    session: Session, sha: str, reachable: set[str]
) -> str | None:
    """Follow CommitRewrite old→new chains from ``sha`` to a reachable commit."""
    seen = {sha}
    current = sha
    for _ in range(100):  # cycle guard
        row = session.exec(
            select(CommitRewrite)
            .where(CommitRewrite.old_sha == current)
            .order_by(CommitRewrite.created_at.desc())  # type: ignore[union-attr]
        ).first()
        if row is None:
            break
        current = row.new_sha
        if current in reachable:
            return current
        if current in seen:
            break
        seen.add(current)
    return current if current in reachable else None


def reconcile_threads(session: Session, repo: pygit2.Repository) -> int:
    """Migrate orphaned threads onto the commit they have become. Returns the
    number of threads migrated. Cheap no-op when nothing is orphaned."""
    threads = list(session.exec(select(Thread)).all())
    reachable = reachable_shas(repo)

    orphans = [
        t
        for t in threads
        if t.commit_sha != WORKING_TREE_SHA and t.commit_sha not in reachable
    ]
    if not orphans:
        return 0

    index = _identity_index(repo, reachable)
    migrated = 0
    for t in orphans:
        target = _follow_rewrites(session, t.commit_sha, reachable)
        if target is None and t.commit_author_email is not None:
            key: IdentityKey = (
                t.commit_subject or "",
                t.commit_author_email or "",
                t.commit_author_time or 0,
            )
            candidates = index.get(key, [])
            if len(candidates) == 1:
                target = candidates[0]
        if target is not None and target != t.commit_sha:
            t.commit_sha = target
            session.add(t)
            migrated += 1
    if migrated:
        session.commit()
    return migrated


def orphaned_threads(session: Session, repo: pygit2.Repository) -> list[Thread]:
    """Threads still not reachable after reconciliation — they need the human
    to reach them via the dedicated panel."""
    reconcile_threads(session, repo)
    reachable = reachable_shas(repo)
    return [
        t
        for t in session.exec(select(Thread)).all()
        if t.commit_sha != WORKING_TREE_SHA and t.commit_sha not in reachable
    ]


def _migrate_versions(session: Session, old_sha: str, new_sha: str) -> None:
    """Move a commit's captured versions onto its rewritten SHA so V1..Vn stay
    one continuous sequence for the logical commit. Renumbers old-then-new."""
    old_versions = list(
        session.exec(
            select(CommitVersion)
            .where(CommitVersion.commit_sha == old_sha)
            .order_by(CommitVersion.version_number)
        ).all()
    )
    if not old_versions:
        return
    existing_new = list(
        session.exec(
            select(CommitVersion)
            .where(CommitVersion.commit_sha == new_sha)
            .order_by(CommitVersion.version_number)
        ).all()
    )
    for i, v in enumerate([*old_versions, *existing_new], start=1):
        v.commit_sha = new_sha
        v.version_number = i
        session.add(v)
    session.flush()


def record_rewrite(
    session: Session, repo: pygit2.Repository, old_sha: str, new_sha: str
) -> int:
    """Record an old→new commit rewrite: carry the commit's version history
    forward onto the new SHA, capture the new content as the next version, and
    reconcile orphaned threads. Returns the number of threads migrated."""
    # Local import avoids a module-level cycle (snapshots is heavier).
    from gitloco.snapshots import capture_version

    session.add(CommitRewrite(old_sha=old_sha, new_sha=new_sha))
    _migrate_versions(session, old_sha, new_sha)
    session.commit()

    # Capture the rewritten commit's content. Dedup means this appends a new
    # version only if the content actually changed (it normally has).
    capture_version(
        repo=repo,
        session=session,
        commit_sha=new_sha,
        trigger="rewrite",
        triggering_thread_id=None,
        triggering_reply_id=None,
    )
    session.commit()
    return reconcile_threads(session, repo)
