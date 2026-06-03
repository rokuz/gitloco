from fastapi import APIRouter, HTTPException, Query, Request

from gitloco.file_history import (
    iter_commits_touching,
    read_file_at,
    working_tree_patch_for,
)
from gitloco.schemas import FileAtOut, FileHistoryCommitOut, FileHistoryOut

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/history", response_model=FileHistoryOut)
def get_file_history(
    request: Request,
    path: str = Query(..., description="Repo-relative file path"),
    since: str | None = Query(
        None, description="Commit SHA to start from (inclusive). Defaults to repo root."
    ),
) -> FileHistoryOut:
    repo = request.app.state.repo
    commits = iter_commits_touching(repo, path, since_sha=since)
    wt = working_tree_patch_for(repo, path)
    return FileHistoryOut(
        file_path=path,
        since=since,
        commits=[
            FileHistoryCommitOut(
                sha=c.sha,
                short_sha=c.short_sha,
                author_name=c.author_name,
                author_email=c.author_email,
                committed_at=c.committed_at,
                subject=c.subject,
                parent_shas=c.parent_shas,
                status=c.status,
                old_path=c.old_path,
                new_path=c.new_path,
                patch_text=c.patch_text,
            )
            for c in commits
        ],
        working_tree_patch=wt,
    )


@router.get("/at", response_model=FileAtOut)
def get_file_at(
    request: Request,
    sha: str = Query(..., description="Commit SHA or 'WORKING_TREE'"),
    path: str = Query(..., description="Repo-relative file path"),
) -> FileAtOut:
    repo = request.app.state.repo
    snap = read_file_at(repo, sha, path)
    if not snap.exists:
        raise HTTPException(status_code=404, detail="file not found at this revision")
    content: str | None = None
    if not snap.is_binary and snap.content is not None:
        content = snap.content.decode("utf-8", errors="replace")
    return FileAtOut(
        file_path=path,
        sha=sha,
        exists=snap.exists,
        is_binary=snap.is_binary,
        content=content,
    )
