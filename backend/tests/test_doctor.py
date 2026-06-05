"""`gitloco doctor` collapses duplicate versions and re-links orphaned threads."""

import subprocess
from pathlib import Path

import pygit2
from sqlmodel import Session, select

from gitloco import doctor
from gitloco import persistence as pc
from gitloco.db import make_engine, session_scope
from gitloco.models import CommitVersion, Reply, Thread


def _git(d: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


def _make_repo(tmp_path: Path) -> tuple[pygit2.Repository, str]:
    d = tmp_path / "repo"
    d.mkdir()
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t.co")
    _git(d, "config", "user.name", "t")
    (d / "a.py").write_text("print(1)\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "feature")
    repo = pygit2.Repository(str(d))
    return repo, str(repo.head.target)


def _amend(repo: Path, content: str) -> str:
    (repo / "a.py").write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--amend", "--no-edit")
    return str(pygit2.Repository(str(repo)).head.target)


def test_doctor_dedups_versions_and_relinks_orphans(tmp_path: Path):
    repo, sha = _make_repo(tmp_path)
    engine = make_engine(tmp_path / "comments.db")

    # A thread on the commit → persistent commit + V1.
    with session_scope(engine) as s:
        pc_id = pc.resolve_pc(s, repo, sha, create=True)
        thread = Thread(
            persistent_commit_id=pc_id,
            commit_hash=sha,
            file_path="a.py",
            line_side="new",
            line_number=1,
        )
        s.add(thread)
        s.flush()
        s.add(Reply(thread_id=thread.id, author="human", body="fix"))

    # Manufacture a duplicate version row for the same (pc, hash).
    with session_scope(engine) as s:
        v1 = s.exec(select(CommitVersion)).first()
        s.add(
            CommitVersion(
                persistent_commit_id=v1.persistent_commit_id,
                version_number=v1.version_number,
                commit_hash=v1.commit_hash,
                subject=v1.subject,
                author_name=v1.author_name,
                author_email=v1.author_email,
                author_time=v1.author_time,
            )
        )

    # Rebase the commit away — old SHA becomes unreachable (orphan candidate),
    # but its identity still matches the new reachable commit.
    new_sha = _amend(tmp_path / "repo", "print(2)\n")

    with session_scope(engine) as s:
        report = doctor.repair(s, repo)

    with Session(engine) as s:
        versions = s.exec(select(CommitVersion)).all()
        hashes = [v.commit_hash for v in versions]
        numbers = sorted(v.version_number for v in versions)

    # Duplicate gone (old SHA once), rewrite re-linked (new SHA present),
    # numbering gapless.
    assert hashes.count(sha) == 1
    assert new_sha in hashes
    assert numbers == [1, 2]
    assert any("duplicate" in line for line in report)
    assert any("re-linked" in line for line in report)


def test_doctor_healthy_db_is_a_noop(tmp_path: Path):
    repo, sha = _make_repo(tmp_path)
    engine = make_engine(tmp_path / "comments.db")
    with session_scope(engine) as s:
        pc.resolve_pc(s, repo, sha, create=True)

    with session_scope(engine) as s:
        report = doctor.repair(s, repo)
    assert report == []  # nothing to fix
    assert doctor.check_integrity(engine) == ["integrity check: ok"]
