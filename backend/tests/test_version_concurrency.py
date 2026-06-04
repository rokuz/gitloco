"""Concurrent requests for the same rewritten commit must not create duplicate
versions (regression for the check-then-insert race in resolve_pc)."""

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pygit2
from sqlmodel import Session, select

from gitloco import persistence as pc
from gitloco.db import make_engine
from gitloco.models import CommitVersion


def _run(repo_dir: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo_dir), *args], check=True, capture_output=True)


def _make_repo(tmp_path: Path) -> tuple[pygit2.Repository, str, str]:
    d = tmp_path / "repo"
    d.mkdir()
    _run(d, "init", "-q")
    _run(d, "config", "user.email", "t@t.co")
    _run(d, "config", "user.name", "t")
    (d / "a.py").write_text("print(1)\n")
    _run(d, "add", "-A")
    _run(d, "commit", "-qm", "feature")
    repo = pygit2.Repository(str(d))
    original = str(repo.head.target)
    # Amend the file to rewrite the commit (same identity → auto-linkable).
    (d / "a.py").write_text("print(2)\n")
    _run(d, "add", "-A")
    _run(d, "commit", "-q", "--amend", "--no-edit")
    rewritten = str(repo.head.target)
    return repo, original, rewritten


def test_concurrent_resolution_creates_one_version(tmp_path: Path):
    repo, original, rewritten = _make_repo(tmp_path)
    engine = make_engine(tmp_path / "comments.db")

    # Seed: a thread on the original commit creates its persistent commit + V1.
    with Session(engine) as s:
        pc.resolve_pc(s, repo, original, create=True)
        s.commit()

    # Many threads concurrently resolve the rewritten hash (the read path that
    # auto-links it) plus an explicit record_rewrite — the exact collision the
    # UI triggers after a rebase.
    def resolve():
        with Session(engine) as s:
            return pc.resolve_pc(s, repo, rewritten, create=False)

    def rewrite():
        with Session(engine) as s:
            pc.record_rewrite(s, repo, original, rewritten)

    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = [ex.submit(resolve if i % 2 else rewrite) for i in range(32)]
        for f in futures:
            f.result()

    with Session(engine) as s:
        versions = s.exec(
            select(CommitVersion).where(CommitVersion.commit_hash == rewritten)
        ).all()
    assert len(versions) == 1, [(v.id, v.version_number) for v in versions]
