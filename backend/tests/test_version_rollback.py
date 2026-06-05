"""version_file_contents returns the writable file content of a version, so an
agent can roll a commit back to it."""

import subprocess
from pathlib import Path

import pygit2
from sqlmodel import Session

from gitloco import persistence as pc
from gitloco.db import make_engine


def _git(d: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


def test_version_file_contents_returns_each_versions_text(tmp_path: Path):
    d = tmp_path / "repo"
    d.mkdir()
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t.co")
    _git(d, "config", "user.name", "t")
    (d / "a.py").write_text("print(1)\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "feature")
    repo = pygit2.Repository(str(d))
    sha = str(repo.head.target)

    engine = make_engine(tmp_path / "comments.db")
    with Session(engine) as s:
        pc.resolve_pc(s, repo, sha, create=True)  # V1
        s.commit()

    # Amend (same identity) → auto-linked V2 with different content.
    (d / "a.py").write_text("print(2)\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-q", "--amend", "--no-edit")
    new_sha = str(pygit2.Repository(str(d)).head.target)
    with Session(engine) as s:
        pc.versions_for_hash(s, repo, new_sha)  # trigger the auto-link
        s.commit()

    with Session(engine) as s:
        v1 = pc.version_file_contents(s, repo, new_sha, 1)
        v2 = pc.version_file_contents(s, repo, new_sha, 2)

    a1 = next(f for f in v1["files"] if f["file_path"] == "a.py")
    a2 = next(f for f in v2["files"] if f["file_path"] == "a.py")
    assert a1["content"] == "print(1)\n" and a1["present"] is True
    assert a2["content"] == "print(2)\n"


def test_version_file_contents_missing_version_is_none(tmp_path: Path):
    d = tmp_path / "repo"
    d.mkdir()
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t.co")
    _git(d, "config", "user.name", "t")
    (d / "a.py").write_text("x\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "c")
    repo = pygit2.Repository(str(d))
    sha = str(repo.head.target)
    engine = make_engine(tmp_path / "comments.db")
    with Session(engine) as s:
        pc.resolve_pc(s, repo, sha, create=True)
        s.commit()
        assert pc.version_file_contents(s, repo, sha, 99) is None
