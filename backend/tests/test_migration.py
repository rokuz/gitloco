"""The old (commit_sha-keyed) schema migrates into the persistent-commit model
without losing threads, replies or version history."""

import sqlite3
from pathlib import Path

from sqlmodel import Session, select

from gitloco.db import make_engine
from gitloco.models import CommitVersion, PersistentCommit, Reply, Thread

_OLD_SCHEMA = """
CREATE TABLE snapshot (id INTEGER PRIMARY KEY, content_hash TEXT UNIQUE,
  file_path TEXT, content BLOB, is_binary BOOLEAN, originating_commit_sha TEXT,
  originating_kind TEXT, created_at TEXT);
CREATE TABLE thread (id INTEGER PRIMARY KEY, commit_sha TEXT, file_path TEXT,
  parent_snapshot_id INT, commit_snapshot_id INT, line_side TEXT, line_number INT,
  status TEXT, created_at TEXT, resolved_at TEXT, commit_subject TEXT,
  commit_author_name TEXT, commit_author_email TEXT, commit_author_time INT);
CREATE TABLE reply (id INTEGER PRIMARY KEY, thread_id INT, author TEXT, body TEXT,
  created_at TEXT);
CREATE TABLE commit_rewrite (id INTEGER PRIMARY KEY, old_sha TEXT, new_sha TEXT,
  created_at TEXT);
CREATE TABLE commit_version (id INTEGER PRIMARY KEY, commit_sha TEXT,
  version_number INT, created_at TEXT, trigger TEXT, triggering_thread_id INT,
  triggering_reply_id INT);
CREATE TABLE commit_version_file (id INTEGER PRIMARY KEY, version_id INT,
  file_path TEXT, status TEXT, old_path TEXT, new_path TEXT,
  parent_snapshot_id INT, commit_snapshot_id INT);
"""


def test_old_db_migrates_to_persistent_model(tmp_path: Path):
    db = tmp_path / "comments.db"
    con = sqlite3.connect(db)
    con.executescript(_OLD_SCHEMA)
    # Commit AAA was rebased to BBB; a thread + 2 replies on AAA; versions on each.
    con.execute(
        "INSERT INTO snapshot VALUES "
        "(1,'h1','f.py',X'7072696e7428290a',0,NULL,'commit','2026-01-01')"
    )
    con.execute(
        "INSERT INTO thread VALUES (1,'AAA','f.py',NULL,NULL,'new',2,'open',"
        "'2026-01-01',NULL,NULL,NULL,NULL,NULL)"
    )
    con.execute("INSERT INTO reply VALUES (1,1,'human','please fix','2026-01-01')")
    con.execute("INSERT INTO reply VALUES (2,1,'agent','done','2026-01-02')")
    con.execute("INSERT INTO commit_rewrite VALUES (1,'AAA','BBB','2026-01-02')")
    con.execute(
        "INSERT INTO commit_version VALUES (1,'AAA',1,'2026-01-01','thread_created',1,NULL)"
    )
    con.execute(
        "INSERT INTO commit_version VALUES (2,'BBB',1,'2026-01-02','rewrite',NULL,NULL)"
    )
    con.execute(
        "INSERT INTO commit_version_file VALUES (1,1,'f.py','modified','f.py','f.py',1,1)"
    )
    con.commit()
    con.close()

    engine = make_engine(db)
    with Session(engine) as s:
        pcs = s.exec(select(PersistentCommit)).all()
        threads = s.exec(select(Thread)).all()
        versions = s.exec(select(CommitVersion)).all()
        replies = s.exec(select(Reply)).all()

    # AAA and BBB are the same logical commit → one persistent commit.
    assert len(pcs) == 1
    assert {v.commit_hash for v in versions} == {"AAA", "BBB"}
    assert len(threads) == 1 and threads[0].persistent_commit_id == pcs[0].id
    assert threads[0].commit_hash == "AAA" and threads[0].status == "open"
    assert sorted(r.body for r in replies) == ["done", "please fix"]
