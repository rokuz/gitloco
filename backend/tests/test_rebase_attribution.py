"""Threads and version history follow a commit across a rebase, via the
persistent-commit model."""

from pathlib import Path

import pygit2
from fastapi.testclient import TestClient


def _amend(repo_dir: Path, new_content: str, *, message=None) -> tuple[str, str]:
    """Simulate `git commit --amend` on HEAD, preserving the author signature
    (so identity auto-linking can match). Returns (old_sha, new_sha)."""
    repo = pygit2.Repository(str(repo_dir))
    head = repo[repo.head.target]
    old_sha = str(head.id)
    (repo_dir / "hello.py").write_text(new_content)
    repo.index.add("hello.py")
    repo.index.write()
    new_id = repo.create_commit(
        None,
        head.author,  # same name/email/time
        pygit2.Signature("Rebaser", "rebase@e.com"),
        message if message is not None else head.message,
        repo.index.write_tree(),
        [p.id for p in head.parents],
    )
    repo.lookup_reference(repo.head.name).set_target(new_id)
    return old_sha, str(new_id)


def _new_thread(client: TestClient, sha: str, body: str = "look here"):
    return client.post(
        "/api/threads",
        json={
            "commit_sha": sha,
            "file_path": "hello.py",
            "line_side": "new",
            "line_number": 1,
            "body": body,
        },
    )


def test_thread_and_versions_follow_an_identity_rebase(
    client: TestClient, latest_sha: str, repo_dir: Path
):
    """No explicit record needed: amending a commit (same author identity) lets
    GitLoco auto-link the new hash, so the thread shows on the new commit and a
    new version appears."""
    tid = _new_thread(client, latest_sha).json()["id"]
    assert [v["version_number"] for v in client.get(
        f"/api/commits/{latest_sha}/versions"
    ).json()] == [1]

    _old, new_sha = _amend(repo_dir, "def greet(name: str) -> None:\n    return None\n")

    on_new = client.get(f"/api/threads?sha={new_sha}").json()
    assert [t["id"] for t in on_new] == [tid]
    # Original (V1) plus the rewrite (V2) both live under the logical commit.
    assert [v["version_number"] for v in client.get(
        f"/api/commits/{new_sha}/versions"
    ).json()] == [1, 2]


def test_explicit_record_rewrite_when_identity_changes(
    client: TestClient, latest_sha: str, repo_dir: Path
):
    """If the amend changes the commit message, identity won't match — but an
    explicit record_commit_rewrite still links it."""
    tid = _new_thread(client, latest_sha).json()["id"]
    old_sha, new_sha = _amend(
        repo_dir, "def greet(n): pass\n", message="totally different subject"
    )

    # Identity differs → not auto-linked yet.
    assert client.get(f"/api/threads?sha={new_sha}").json() == []

    r = client.post(
        "/api/commits/rewrites", json={"old_sha": old_sha, "new_sha": new_sha}
    )
    assert r.status_code == 200 and r.json()["linked"] is True

    assert [t["id"] for t in client.get(f"/api/threads?sha={new_sha}").json()] == [tid]
    assert [v["version_number"] for v in client.get(
        f"/api/commits/{new_sha}/versions"
    ).json()] == [1, 2]


def test_compare_two_versions_shows_the_fix(
    client: TestClient, latest_sha: str, repo_dir: Path
):
    _new_thread(client, latest_sha)
    _old, new_sha = _amend(
        repo_dir, "def greet(name: str) -> None:\n    print('hi', name)\n"
    )
    # Trigger the auto-link by reading versions.
    versions = client.get(f"/api/commits/{new_sha}/versions").json()
    assert [v["version_number"] for v in versions] == [1, 2]
    cmp = client.get(f"/api/commits/{new_sha}/compare?from=V1&to=V2").json()
    patches = "\n".join(f["patch_text"] for f in cmp["files"])
    assert "print('hi', name)" in patches


def test_resolve_works_after_rebase(
    client: TestClient, latest_sha: str, repo_dir: Path
):
    tid = _new_thread(client, latest_sha).json()["id"]
    _old, new_sha = _amend(repo_dir, "def greet(name: str) -> None:\n    pass\n")
    assert [t["id"] for t in client.get(f"/api/threads?sha={new_sha}").json()] == [tid]
    r = client.post(f"/api/threads/{tid}/resolve")
    assert r.status_code == 200 and r.json()["status"] == "resolved"
