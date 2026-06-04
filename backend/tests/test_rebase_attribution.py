"""Threads must stay attached to a commit after it's rebased to a new SHA."""

from pathlib import Path

import pygit2
from fastapi.testclient import TestClient


def _amend_head(repo_dir: Path, new_content: str) -> tuple[str, str]:
    """Simulate `git commit --amend` on HEAD: same author (name/email/time) and
    message, new tree. Returns (old_sha, new_sha)."""
    repo = pygit2.Repository(str(repo_dir))
    head = repo[repo.head.target]
    old_sha = str(head.id)

    (repo_dir / "hello.py").write_text(new_content)
    repo.index.add("hello.py")
    repo.index.write()
    tree = repo.index.write_tree()

    # Preserve the original author signature (incl. time) — git does this on
    # amend/rebase; it's what identity matching relies on. Create detached
    # (reference_name=None) then move the branch ref, i.e. replace HEAD.
    new_id = repo.create_commit(
        None,
        head.author,  # same name/email/time
        repo.default_signature,  # committer may differ
        head.message,  # same message
        tree,
        [p.id for p in head.parents],
    )
    repo.lookup_reference(repo.head.name).set_target(new_id)
    return old_sha, str(new_id)


def _new_thread(client: TestClient, sha: str):
    return client.post(
        "/api/threads",
        json={
            "commit_sha": sha,
            "file_path": "hello.py",
            "line_side": "new",
            "line_number": 1,
            "body": "add a docstring",
        },
    )


def test_thread_reattaches_by_identity_after_rebase(
    client: TestClient, latest_sha: str, repo_dir: Path
):
    tid = _new_thread(client, latest_sha).json()["id"]
    assert len(client.get(f"/api/threads?sha={latest_sha}").json()) == 1

    old_sha, new_sha = _amend_head(
        repo_dir, "def greet(name: str) -> None:\n    '''hi'''\n    print(name)\n"
    )
    assert old_sha == latest_sha and new_sha != old_sha

    # Old SHA no longer has the thread surfaced…
    assert client.get(f"/api/threads?sha={old_sha}").json() == []
    # …it auto-migrated to the new SHA by commit identity.
    on_new = client.get(f"/api/threads?sha={new_sha}").json()
    assert len(on_new) == 1
    assert on_new[0]["id"] == tid


def test_explicit_record_commit_rewrite_reattaches(
    client: TestClient, latest_sha: str, repo_dir: Path
):
    tid = _new_thread(client, latest_sha).json()["id"]

    # Amend AND change the subject so identity matching can't help — only the
    # explicit rewrite record can re-attach the thread.
    repo = pygit2.Repository(str(repo_dir))
    head = repo[repo.head.target]
    old_sha = str(head.id)
    (repo_dir / "hello.py").write_text("def greet(name: str) -> None:\n    pass\n")
    repo.index.add("hello.py")
    repo.index.write()
    new_id = repo.create_commit(
        None, head.author, repo.default_signature,
        "Completely different subject", repo.index.write_tree(),
        [p.id for p in head.parents],
    )
    repo.lookup_reference(repo.head.name).set_target(new_id)
    new_sha = str(new_id)

    # Without a record, identity match fails → thread is an orphan.
    assert client.get(f"/api/threads?sha={new_sha}").json() == []
    orphans = client.get("/api/threads/orphans").json()
    assert [t["id"] for t in orphans] == [tid]

    # Record the rewrite → thread migrates to the new SHA.
    r = client.post(
        "/api/commits/rewrites", json={"old_sha": old_sha, "new_sha": new_sha}
    )
    assert r.status_code == 200
    assert r.json()["migrated_threads"] == 1
    on_new = client.get(f"/api/threads?sha={new_sha}").json()
    assert [t["id"] for t in on_new] == [tid]
    assert client.get("/api/threads/orphans").json() == []


def test_resolve_still_works_after_reattach(
    client: TestClient, latest_sha: str, repo_dir: Path
):
    tid = _new_thread(client, latest_sha).json()["id"]
    _, new_sha = _amend_head(repo_dir, "def greet(name: str) -> None:\n    return None\n")
    # Thread surfaced on the new SHA, and the human can resolve it.
    assert [t["id"] for t in client.get(f"/api/threads?sha={new_sha}").json()] == [tid]
    r = client.post(f"/api/threads/{tid}/resolve")
    assert r.status_code == 200 and r.json()["status"] == "resolved"
