#!/usr/bin/env python
"""One-off migration: old (commit_sha-keyed) comments.db -> persistent-commit model.

This is NOT part of the shipped app (the app ships the persistent-commit schema as
its initial design). It exists only to carry forward the two real pre-existing DBs:
GitLoco's own .gitloco/comments.db and any comments.db a user kept from an older build.

Usage:
    uv run python scripts/migrate_old_db.py path/to/comments.db

It backs up the original to <db>.pre-migration.bak, then rewrites it in place.
Re-running on an already-migrated DB is a no-op (detected by schema).
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

# Import the app's models so the fresh DB is built from the canonical schema.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
from gitloco.db import make_engine  # noqa: E402


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def _is_old_schema(con: sqlite3.Connection) -> bool:
    cols = _columns(con, "thread")
    return "commit_sha" in cols and "persistent_commit_id" not in cols


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, x: str) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: str) -> str:
        self.add(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


def migrate(db_path: Path) -> None:
    old = sqlite3.connect(db_path)
    old.row_factory = sqlite3.Row

    if not _is_old_schema(old):
        print(f"{db_path} is already on the persistent-commit schema — nothing to do.")
        old.close()
        return

    # --- read everything from the old DB ---
    snapshots = old.execute("SELECT * FROM snapshot").fetchall()
    threads = old.execute("SELECT * FROM thread").fetchall()
    replies = old.execute("SELECT * FROM reply").fetchall()
    versions = old.execute("SELECT * FROM commit_version").fetchall()
    version_files = old.execute("SELECT * FROM commit_version_file").fetchall()
    try:
        rewrites = old.execute("SELECT * FROM commit_rewrite").fetchall()
    except sqlite3.OperationalError:
        rewrites = []
    old.close()

    # --- group commit hashes into persistent commits (rewrite chains collapse) ---
    uf = _UnionFind()
    for t in threads:
        uf.add(t["commit_sha"])
    for v in versions:
        uf.add(v["commit_sha"])
    for rw in rewrites:
        uf.union(rw["old_sha"], rw["new_sha"])

    roots = sorted({uf.find(h) for h in uf.parent})
    pc_of_root = {root: i + 1 for i, root in enumerate(roots)}
    pc_of_hash = {h: pc_of_root[uf.find(h)] for h in uf.parent}

    # identity (subject/author) lived on the old thread rows; index it by hash
    identity: dict[str, sqlite3.Row] = {}
    for t in threads:
        h = t["commit_sha"]
        if h not in identity and t["commit_subject"] is not None:
            identity[h] = t

    # renumber versions 1..N within each persistent commit, ordered by time
    versions_sorted = sorted(versions, key=lambda v: (v["created_at"] or "", v["id"]))
    next_number: dict[int, int] = {}
    new_version_number: dict[int, int] = {}
    for v in versions_sorted:
        pc = pc_of_hash[v["commit_sha"]]
        next_number[pc] = next_number.get(pc, 0) + 1
        new_version_number[v["id"]] = next_number[pc]

    # --- build a fresh new-schema DB next to the target, then swap it in ---
    tmp_dir = Path(tempfile.mkdtemp())
    new_path = tmp_dir / "migrated.db"
    make_engine(new_path)  # clean create_all of the canonical schema

    new = sqlite3.connect(new_path)
    new.execute("PRAGMA foreign_keys=OFF")

    for root in roots:
        new.execute(
            "INSERT INTO persistent_commit (id, created_at) VALUES (?, ?)",
            (pc_of_root[root], _earliest_created_at(root, uf, versions, threads)),
        )

    for s in snapshots:
        new.execute(
            "INSERT INTO snapshot (id, content_hash, file_path, content, is_binary, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (s["id"], s["content_hash"], s["file_path"], s["content"],
             s["is_binary"], s["created_at"]),
        )

    for v in versions:
        ident = identity.get(v["commit_sha"])
        new.execute(
            "INSERT INTO commit_version (id, persistent_commit_id, version_number, "
            "commit_hash, created_at, subject, author_name, author_email, author_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                v["id"], pc_of_hash[v["commit_sha"]], new_version_number[v["id"]],
                v["commit_sha"], v["created_at"],
                ident["commit_subject"] if ident else None,
                ident["commit_author_name"] if ident else None,
                ident["commit_author_email"] if ident else None,
                ident["commit_author_time"] if ident else None,
            ),
        )

    for f in version_files:
        new.execute(
            "INSERT INTO commit_version_file (id, version_id, file_path, status, "
            "old_path, new_path, parent_snapshot_id, commit_snapshot_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f["id"], f["version_id"], f["file_path"], f["status"], f["old_path"],
             f["new_path"], f["parent_snapshot_id"], f["commit_snapshot_id"]),
        )

    for t in threads:
        new.execute(
            "INSERT INTO thread (id, persistent_commit_id, commit_hash, file_path, "
            "line_side, line_number, status, created_at, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t["id"], pc_of_hash[t["commit_sha"]], t["commit_sha"], t["file_path"],
             t["line_side"], t["line_number"], t["status"], t["created_at"],
             t["resolved_at"]),
        )

    for r in replies:
        new.execute(
            "INSERT INTO reply (id, thread_id, author, body, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (r["id"], r["thread_id"], r["author"], r["body"], r["created_at"]),
        )

    new.commit()
    new.close()

    backup = db_path.with_suffix(db_path.suffix + ".pre-migration.bak")
    shutil.copy2(db_path, backup)
    shutil.move(str(new_path), str(db_path))
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print(
        f"Migrated {db_path}\n"
        f"  persistent commits: {len(roots)}\n"
        f"  versions: {len(versions)}  threads: {len(threads)}  "
        f"replies: {len(replies)}\n"
        f"  backup: {backup}"
    )


def _earliest_created_at(root, uf, versions, threads):
    times = [
        row["created_at"]
        for row in (*versions, *threads)
        if uf.find(row["commit_sha"]) == root and row["created_at"]
    ]
    return min(times) if times else None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    target = Path(sys.argv[1]).expanduser()
    if not target.exists():
        print(f"No such file: {target}")
        sys.exit(1)
    migrate(target)
