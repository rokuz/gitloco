from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from gitloco import models  # noqa: F401  — ensure tables are registered

# Tables whose schema changed in the move to the persistent-commit model.
_RENAMED = ["thread", "commit_version", "commit_version_file", "snapshot"]


def _needs_persistent_migration(engine: Engine) -> bool:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "thread" not in tables:
        return False  # fresh database
    cols = {c["name"] for c in insp.get_columns("thread")}
    # Old schema had thread.commit_sha; new schema has thread.persistent_commit_id.
    return "commit_sha" in cols and "persistent_commit_id" not in cols


def _migrate_to_persistent(engine: Engine) -> None:
    """One-time migration of an old (commit_sha-keyed) database to the
    persistent-commit model, preserving threads, replies and versions."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())

    with engine.begin() as conn:
        for t in _RENAMED:
            if t in tables:
                conn.execute(text(f'ALTER TABLE "{t}" RENAME TO "_old_{t}"'))

    SQLModel.metadata.create_all(engine)  # create the new-schema tables

    with engine.begin() as conn:
        _copy_old_data(conn, tables)
        for t in [*[f"_old_{t}" for t in _RENAMED], "commit_rewrite"]:
            conn.execute(text(f'DROP TABLE IF EXISTS "{t}"'))


def _copy_old_data(conn, old_tables: set[str]) -> None:
    # Group commit hashes into logical commits via the old rewrite chain.
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    if "commit_rewrite" in old_tables:
        for old_sha, new_sha in conn.execute(
            text("SELECT old_sha, new_sha FROM commit_rewrite")
        ):
            union(old_sha, new_sha)

    versions = list(
        conn.execute(
            text(
                "SELECT id, commit_sha, version_number, created_at "
                "FROM _old_commit_version ORDER BY created_at, id"
            )
        )
    )
    threads = list(
        conn.execute(
            text(
                "SELECT id, commit_sha, file_path, line_side, line_number, "
                "status, created_at, resolved_at FROM _old_thread"
            )
        )
    )

    # Persistent commit per group; map every hash → persistent_commit_id.
    pc_id_by_group: dict[str, int] = {}

    def pc_for(commit_hash: str) -> int:
        root = find(commit_hash)
        if root not in pc_id_by_group:
            res = conn.execute(
                text("INSERT INTO persistent_commit (created_at) VALUES (:t)"),
                {"t": _now_iso()},
            )
            pc_id_by_group[root] = res.lastrowid
        return pc_id_by_group[root]

    # snapshots: copy compatible columns.
    if "_old_snapshot" in {f"_old_{t}" for t in _RENAMED}:
        conn.execute(
            text(
                "INSERT INTO snapshot (id, content_hash, file_path, content, "
                "is_binary, created_at) SELECT id, content_hash, file_path, "
                "content, is_binary, created_at FROM _old_snapshot"
            )
        )

    # versions, renumbered per persistent commit (chronological order).
    new_version_id: dict[int, int] = {}
    counter: dict[int, int] = {}
    for old_id, commit_sha, _vn, created_at in versions:
        pc = pc_for(commit_sha)
        counter[pc] = counter.get(pc, 0) + 1
        res = conn.execute(
            text(
                "INSERT INTO commit_version (persistent_commit_id, version_number, "
                "commit_hash, created_at) VALUES (:pc, :vn, :h, :t)"
            ),
            {"pc": pc, "vn": counter[pc], "h": commit_sha, "t": created_at},
        )
        new_version_id[old_id] = res.lastrowid

    for old_vid, new_vid in new_version_id.items():
        for row in conn.execute(
            text(
                "SELECT file_path, status, old_path, new_path, parent_snapshot_id, "
                "commit_snapshot_id FROM _old_commit_version_file WHERE version_id = :v"
            ),
            {"v": old_vid},
        ):
            conn.execute(
                text(
                    "INSERT INTO commit_version_file (version_id, file_path, status, "
                    "old_path, new_path, parent_snapshot_id, commit_snapshot_id) "
                    "VALUES (:v, :fp, :st, :op, :np, :ps, :cs)"
                ),
                {
                    "v": new_vid, "fp": row[0], "st": row[1], "op": row[2],
                    "np": row[3], "ps": row[4], "cs": row[5],
                },
            )

    # threads (keep ids so reply.thread_id stays valid).
    for tid, commit_sha, fp, side, line, status, created, resolved in threads:
        conn.execute(
            text(
                "INSERT INTO thread (id, persistent_commit_id, commit_hash, file_path, "
                "line_side, line_number, status, created_at, resolved_at) VALUES "
                "(:id, :pc, :h, :fp, :side, :line, :st, :c, :r)"
            ),
            {
                "id": tid, "pc": pc_for(commit_sha), "h": commit_sha, "fp": fp,
                "side": side, "line": line, "st": status, "c": created, "r": resolved,
            },
        )


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    if _needs_persistent_migration(engine):
        _migrate_to_persistent(engine)
    SQLModel.metadata.create_all(engine)  # create tables for a fresh database
    return engine


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
