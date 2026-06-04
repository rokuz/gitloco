from fastapi.testclient import TestClient


def test_commits_endpoint_lists_commits_and_working_tree(client: TestClient):
    body = client.get("/api/commits").json()
    commits = body["commits"]
    assert body["has_working_tree_changes"] is True
    assert body["branch"] == "main"
    # Working-tree pseudo-entry sits at the top.
    assert commits[0]["is_working_tree"] is True
    assert commits[0]["sha"] == "WORKING_TREE"
    # Two real commits in topological order.
    real = [c for c in commits if not c["is_working_tree"]]
    assert [c["subject"] for c in real] == ["Type hints", "Initial"]
    assert real[0]["parent_shas"] == [real[1]["sha"]]


def test_diff_endpoint_returns_per_file_unified_patch(
    client: TestClient, latest_sha: str
):
    diff = client.get(f"/api/commits/{latest_sha}/diff").json()
    assert diff["sha"] == latest_sha
    assert len(diff["files"]) == 1
    f = diff["files"][0]
    assert f["new_path"] == "hello.py" and f["old_path"] == "hello.py"
    assert f["status"] == "modified"
    assert "name: str" in f["patch_text"]


def test_working_tree_diff_picks_up_untracked_file(client: TestClient):
    diff = client.get("/api/commits/WORKING_TREE/diff").json()
    paths = [f["new_path"] for f in diff["files"]]
    assert "scratch.txt" in paths
    scratch = next(f for f in diff["files"] if f["new_path"] == "scratch.txt")
    assert scratch["status"] == "added"
    assert "wip" in scratch["patch_text"]
