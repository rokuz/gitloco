"""Shared pytest fixtures — produce a populated temporary git repo and a
``TestClient`` wired against the FastAPI app for that repo.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pygit2
import pytest
from fastapi.testclient import TestClient

from gitloco.app import create_app
from gitloco.config import Settings


@pytest.fixture
def repo_dir(tmp_path: Path) -> Iterator[Path]:
    """Create a tmp git repo with two commits + an uncommitted file."""
    path = tmp_path / "repo"
    path.mkdir()
    repo = pygit2.init_repository(str(path), initial_head="main")
    sig = pygit2.Signature("Test", "t@e.com")

    (path / "hello.py").write_text("def greet(name):\n    print(name)\n")
    repo.index.add("hello.py")
    repo.index.write()
    tree = repo.index.write_tree()
    repo.create_commit("HEAD", sig, sig, "Initial", tree, [])

    (path / "hello.py").write_text(
        "def greet(name: str) -> None:\n    print(name)\n"
    )
    repo.index.add("hello.py")
    repo.index.write()
    tree2 = repo.index.write_tree()
    parent = repo.head.target
    repo.create_commit("HEAD", sig, sig, "Type hints", tree2, [parent])

    # Leave a working-tree change so the WORKING_TREE pseudo-entry shows up.
    (path / "scratch.txt").write_text("wip\n")

    yield path

    # tmp_path cleanup is handled by pytest, but pygit2 may leave file
    # handles on Windows — best-effort.
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def client(repo_dir: Path) -> Iterator[TestClient]:
    settings = Settings.for_repo(repo_dir)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def latest_sha(client: TestClient) -> str:
    """Return the SHA of the most recent real commit (not WORKING_TREE)."""
    commits = client.get("/api/commits").json()["commits"]
    return next(c["sha"] for c in commits if not c["is_working_tree"])
