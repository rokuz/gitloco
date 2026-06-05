"""`gitloco doctor` — check and repair a GitLoco database.

All operations are idempotent: running doctor on a healthy database is a no-op.
It fixes everything it safely can and returns a human-readable report.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import groupby

import pygit2
from sqlalchemy import Engine
from sqlmodel import Session, select

from gitloco import persistence as pc
from gitloco.models import CommitVersion, CommitVersionFile
from gitloco.repo import WORKING_TREE_SHA


def _delete_version(session: Session, version: CommitVersion) -> None:
    for f in session.exec(
        select(CommitVersionFile).where(CommitVersionFile.version_id == version.id)
    ).all():
        session.delete(f)
    session.delete(version)


def _renumber_versions(session: Session) -> None:
    """Make version_number a gapless 1..N within each persistent commit."""
    versions = session.exec(
        select(CommitVersion).order_by(
            CommitVersion.persistent_commit_id,
            CommitVersion.version_number,
            CommitVersion.id,
        )
    ).all()
    counters: dict[int, int] = defaultdict(int)
    for v in versions:
        counters[v.persistent_commit_id] += 1
        if v.version_number != counters[v.persistent_commit_id]:
            v.version_number = counters[v.persistent_commit_id]
            session.add(v)
    session.flush()


def _dedup_real_versions(session: Session) -> int:
    """Collapse versions that share a (persistent commit, real SHA) — the
    historical check-then-insert duplicates. Keeps the lowest-id row."""
    groups: dict[tuple[int, str], list[CommitVersion]] = defaultdict(list)
    for v in session.exec(select(CommitVersion).order_by(CommitVersion.id)).all():
        if v.commit_hash != WORKING_TREE_SHA:
            groups[(v.persistent_commit_id, v.commit_hash)].append(v)
    removed = 0
    for versions in groups.values():
        for dup in versions[1:]:  # keep versions[0] (lowest id)
            _delete_version(session, dup)
            removed += 1
    return removed


def _dedup_working_tree(session: Session) -> int:
    """Drop working-tree versions whose content matches the kept one before
    them (duplicate content states left by the old concurrency bug)."""
    rows = session.exec(
        select(CommitVersion)
        .where(CommitVersion.commit_hash == WORKING_TREE_SHA)
        .order_by(
            CommitVersion.persistent_commit_id,
            CommitVersion.version_number,
            CommitVersion.id,
        )
    ).all()
    removed = 0
    for _pc_id, group in groupby(rows, key=lambda v: v.persistent_commit_id):
        prev_fp = None
        for v in group:
            fp = pc._fingerprint(session, v)
            if fp == prev_fp:
                _delete_version(session, v)
                removed += 1
            else:
                prev_fp = fp
    return removed


def repair(session: Session, repo: pygit2.Repository) -> list[str]:
    """Run all ORM-level repairs, returning report lines."""
    report: list[str] = []

    removed = _dedup_real_versions(session) + _dedup_working_tree(session)
    if removed:
        session.flush()
        _renumber_versions(session)
        # Persist now: the relink step below calls resolve_pc, which rolls the
        # session back to a fresh snapshot and would otherwise discard these.
        session.commit()
        report.append(f"removed {removed} duplicate commit version(s)")

    # Re-link rebased commits whose threads look orphaned. orphaned_threads
    # reconciles by identity as a side effect and returns what's still orphaned.
    reachable = pc.reachable_shas(repo)
    before = {t.id for t in pc._current_orphans(session, reachable)}
    if before:
        remaining = {t.id for t in pc.orphaned_threads(session, repo)}
        relinked = len(before - remaining)
        if relinked:
            report.append(f"re-linked {relinked} orphaned thread(s) to their commit")
        if remaining:
            report.append(
                f"{len(remaining)} thread(s) remain orphaned — their commit is "
                "no longer reachable from HEAD (resolve them in the UI)"
            )

    return report


def check_integrity(engine: Engine) -> list[str]:
    """SQLite integrity check + VACUUM (reclaim space). Engine-level: VACUUM
    cannot run inside a transaction."""
    report: list[str] = []
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        rows = cur.execute("PRAGMA integrity_check").fetchall()
        result = [r[0] for r in rows]
        if result == ["ok"]:
            report.append("integrity check: ok")
        else:
            report.append("integrity check found problems: " + "; ".join(result))
        cur.execute("VACUUM")
        raw.commit()
        cur.close()
    finally:
        raw.close()
    return report
