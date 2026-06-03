from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from gitloco.diff import get_diff
from gitloco.repo import (
    WORKING_TREE_SHA,
    has_working_tree_changes,
    list_commits,
)
from gitloco.schemas import CommitDiffOut, CommitListOut, CommitOut, FileDiffOut

router = APIRouter(prefix="/api", tags=["commits"])


@router.get("/commits", response_model=CommitListOut)
def get_commits(request: Request) -> CommitListOut:
    repo = request.app.state.repo
    commits = [
        CommitOut(
            sha=c.sha,
            short_sha=c.short_sha,
            author_name=c.author_name,
            author_email=c.author_email,
            committed_at=c.committed_at,
            subject=c.subject,
            parent_shas=c.parent_shas,
        )
        for c in list_commits(repo)
    ]
    dirty = has_working_tree_changes(repo)
    if dirty:
        commits.insert(
            0,
            CommitOut(
                sha=WORKING_TREE_SHA,
                short_sha="WORKING",
                author_name="(working tree)",
                author_email="",
                committed_at=datetime.now(timezone.utc),
                subject="Uncommitted changes",
                parent_shas=[],
                is_working_tree=True,
            ),
        )
    return CommitListOut(commits=commits, has_working_tree_changes=dirty)


@router.get("/commits/{sha}/diff", response_model=CommitDiffOut)
def get_commit_diff(sha: str, request: Request) -> CommitDiffOut:
    repo = request.app.state.repo
    try:
        files = get_diff(repo, sha)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"commit {sha} not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return CommitDiffOut(
        sha=sha,
        files=[
            FileDiffOut(
                old_path=f.old_path,
                new_path=f.new_path,
                status=f.status,
                is_binary=f.is_binary,
                patch_text=f.patch_text,
            )
            for f in files
        ],
    )
