from fastapi.testclient import TestClient


def _new_thread(client: TestClient, sha: str, body: str = "look at this"):
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


def test_human_creates_thread_with_root_reply(client: TestClient, latest_sha: str):
    r = _new_thread(client, latest_sha, "consider adding a docstring")
    assert r.status_code == 201
    thread = r.json()
    assert thread["status"] == "open"
    assert thread["commit_sha"] == latest_sha
    assert len(thread["replies"]) == 1
    assert thread["replies"][0]["author"] == "human"


def test_agent_cannot_start_a_thread(client: TestClient, latest_sha: str):
    r = client.post(
        "/api/threads",
        headers={"X-GitLoco-Author": "agent"},
        json={
            "commit_sha": latest_sha,
            "file_path": "hello.py",
            "line_side": "new",
            "line_number": 1,
            "body": "I noticed something",
        },
    )
    assert r.status_code == 403


def test_agent_can_reply_human_can_resolve(client: TestClient, latest_sha: str):
    tid = _new_thread(client, latest_sha).json()["id"]
    # Agent replies.
    r = client.post(
        f"/api/threads/{tid}/replies",
        headers={"X-GitLoco-Author": "agent"},
        json={"body": "fixed in next commit"},
    )
    assert r.status_code == 200
    authors = [reply["author"] for reply in r.json()["replies"]]
    assert authors == ["human", "agent"]

    # Agent cannot resolve.
    r = client.post(
        f"/api/threads/{tid}/resolve", headers={"X-GitLoco-Author": "agent"}
    )
    assert r.status_code == 403

    # Human can.
    r = client.post(f"/api/threads/{tid}/resolve")
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"

    # Reply on a resolved thread is rejected.
    r = client.post(f"/api/threads/{tid}/replies", json={"body": "wait"})
    assert r.status_code == 409


def test_comments_do_not_multiply_versions(client: TestClient, latest_sha: str):
    """Versions track content states, not comments: thread creation captures V1
    and further comments on the (unchanged) commit add no versions."""
    tid = _new_thread(client, latest_sha).json()["id"]
    versions = client.get(f"/api/commits/{latest_sha}/versions").json()
    assert [v["version_number"] for v in versions] == [1]

    # Three more comments, commit content unchanged → still just V1.
    client.post(f"/api/threads/{tid}/replies", json={"body": "one more thing"})
    client.post(f"/api/threads/{tid}/replies", json={"body": "and another"})
    _new_thread(client, latest_sha, "separate comment")
    versions = client.get(f"/api/commits/{latest_sha}/versions").json()
    assert [v["version_number"] for v in versions] == [1]


def test_agent_reply_does_not_create_new_version(
    client: TestClient, latest_sha: str
):
    tid = _new_thread(client, latest_sha).json()["id"]
    client.post(
        f"/api/threads/{tid}/replies",
        headers={"X-GitLoco-Author": "agent"},
        json={"body": "done"},
    )
    versions = client.get(f"/api/commits/{latest_sha}/versions").json()
    assert [v["version_number"] for v in versions] == [1]
